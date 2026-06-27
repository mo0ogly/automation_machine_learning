// Bundle Monaco locally (no CDN) and wire its web workers for Vite.
//
// By default @monaco-editor/react fetches Monaco from a CDN at runtime, which
// breaks offline use and makes the editor init asynchronous. Pointing the loader
// at a locally-bundled Monaco makes init local and deterministic.
//
// We import the lean `editor.api` (not the full `monaco-editor` index, which
// ships every language) and register only the two languages we use: markdown
// (basic tokenisation, no worker) and json (json.worker for validation). The
// `?worker` imports let Vite bundle Monaco's web workers.
import { loader } from '@monaco-editor/react';
import * as monaco from 'monaco-editor/esm/vs/editor/editor.api';
import editorWorker from 'monaco-editor/esm/vs/editor/editor.worker?worker';
import jsonWorker from 'monaco-editor/esm/vs/language/json/json.worker?worker';
import 'monaco-editor/esm/vs/language/json/monaco.contribution';
import 'monaco-editor/esm/vs/basic-languages/markdown/markdown.contribution';

self.MonacoEnvironment = {
  getWorker(_workerId, label) {
    if (label === 'json') return new jsonWorker();
    return new editorWorker();
  },
};

loader.config({ monaco });
