// The code route's editor: the CodeMirror that PyScript bundles for its own py-editor, with
// Python highlighting and line numbers. app/editor.py drives it through pyscript.js_modules.
//
// create(host, text, changed) puts an editor holding `text` in `host` and calls changed() after
// every edit. It returns the editor's handle, which it also keeps as `host.editor` for the
// browser tests:
//   getText()       the text
//   setText(text)   replaces the whole text, as typing would, so changed() is called
//   markLine(n)     marks line n (from 1) with the class error-line and scrolls it into view;
//                   null or undefined clears the mark, and so does editing that line
//   revealMark()    scrolls the marked line, if there is one, into view
import { codemirror } from "../vendor/pyscript/core.js";

const [
  { basicSetup, EditorView },
  { EditorState, StateEffect, StateField },
  { python },
  { indentUnit },
  { Decoration, keymap },
  { indentWithTab },
] = await Promise.all([
  codemirror.core,
  codemirror.state,
  codemirror.python,
  codemirror.language,
  codemirror.view,
  codemirror.commands,
]);

// Python's usual indent, and the starting code's.
const INDENT = "    ";

const setMark = StateEffect.define();
const MARK = Decoration.line({ class: "error-line" });

// The start of the marked line, or null.
function markedAt(marks) {
  return marks.size ? marks.iter().from : null;
}

// The marked line moves with lines added or taken away around it, and goes when its own text
// changes or it is replaced.
const marked = StateField.define({
  create: () => Decoration.none,
  update(marks, transaction) {
    const at = markedAt(marks);
    if (transaction.docChanged && at !== null) {
      const old = transaction.startState.doc.lineAt(at);
      // Where the line's text starts, after its indent. Enter there, or anywhere before it,
      // may replace the indent but pushes the text down whole.
      const start = old.from + /^\s*/.exec(old.text)[0].length;
      let replaced = false;
      transaction.changes.iterChangedRanges((fromA, toA) => {
        replaced ||= fromA < old.to && toA > start;
      });
      const line = transaction.newDoc.lineAt(transaction.changes.mapPos(start, 1));
      marks = !replaced && line.text === old.text
        ? Decoration.set([MARK.range(line.from)])
        : Decoration.none;
    }
    for (const effect of transaction.effects) {
      if (effect.is(setMark)) {
        marks = effect.value === null ? Decoration.none : Decoration.set([MARK.range(effect.value)]);
      }
    }
    return marks;
  },
  provide: (field) => EditorView.decorations.from(field),
});

export function create(host, text, changed) {
  const view = new EditorView({
    parent: host,
    doc: text,
    extensions: [
      basicSetup,
      // Escape, then Tab, still moves on from the editor.
      keymap.of([indentWithTab]),
      python(),
      indentUnit.of(INDENT),
      EditorState.tabSize.of(INDENT.length),
      marked,
      EditorView.contentAttributes.of({ "aria-label": "Your Python code" }),
      EditorView.updateListener.of((update) => {
        if (update.docChanged) changed();
      }),
    ],
  });
  const handle = {
    getText: () => view.state.doc.toString(),
    setText(text) {
      view.dispatch({ changes: { from: 0, to: view.state.doc.length, insert: text } });
    },
    markLine(number) {
      if (number === null || number === undefined) {
        view.dispatch({ effects: setMark.of(null) });
        return;
      }
      const { doc } = view.state;
      const line = doc.line(Math.min(Math.max(Math.trunc(number), 1), doc.lines));
      view.dispatch({ effects: [setMark.of(line.from), EditorView.scrollIntoView(line.from)] });
    },
    revealMark() {
      const at = markedAt(view.state.field(marked));
      if (at !== null) view.dispatch({ effects: EditorView.scrollIntoView(at) });
    },
  };
  host.editor = handle;
  return handle;
}
