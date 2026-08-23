// Runway browser engine: the real pipeline, in WebAssembly. Files never leave the machine.
window.Engine = (() => {
  let py = null, ready = false, loading = null;
  const PYODIDE = "https://cdn.jsdelivr.net/pyodide/v314.0.5/full/pyodide.mjs";
  async function init(progress) {
    if (ready) return;
    if (loading) return loading;
    loading = (async () => {
      progress("downloading the Python runtime (~15 MB, once per session)");
      const { loadPyodide } = await import(PYODIDE);
      py = await loadPyodide();
      progress("loading packages: yaml, xlsx, html, pdf, imaging");
      await py.loadPackage(["micropip", "pyyaml", "beautifulsoup4", "cryptography", "pillow"]);
      await py.runPythonAsync('import micropip\nawait micropip.install(["pdfplumber==0.9.0","openpyxl"])');
      progress("mounting the pipeline");
      const list = await (await fetch("engine/files.json")).json();
      const mk = d => { try { py.FS.mkdirTree(d) } catch (e) {} };
      mk("/app/src"); mk("/app/config");
      for (const rel of list) {
        const buf = new Uint8Array(await (await fetch("engine/py/" + rel)).arrayBuffer());
        py.FS.writeFile("/app/" + rel, buf);
      }
      ready = true;
      progress("engine ready");
    })();
    try { await loading } finally { loading = null }
  }
  async function run(exId, files, progress) {
    await init(progress);
    const ws = "w_" + exId.replace(/[^a-z0-9]/gi, "");
    const raw = "/app/workspaces/" + ws + "/raw";
    try { py.FS.mkdirTree(raw) } catch (e) {}
    for (const f of py.FS.readdir(raw)) if (f !== "." && f !== "..") py.FS.unlink(raw + "/" + f);
    for (const f of files) py.FS.writeFile(raw + "/" + f.name, f.bytes);
    progress("running the seven stages on " + files.length + " file(s)");
    const out = await py.runPythonAsync(
      'import sys, json, importlib\n' +
      'sys.path.insert(0, "/app")\n' +
      'import web_run\n' +
      'r = web_run.run(' + JSON.stringify(ws) + ')\n' +
      'json.dumps({"summary": r["summary"], "report": r["report"], ' +
      '"facts": {"Recommendation": r["summary"]["recommendation"] or "none", ' +
      '"Ranking": " > ".join(r["summary"]["ranking"]) or "-", ' +
      '"Deterministic fields": r["summary"]["det"], ' +
      '"Unresolved": r["summary"]["unresolved"], ' +
      '"Runtime": str(r["summary"]["seconds"]) + "s (in this browser)"}})'
    );
    return JSON.parse(out);
  }
  return { init, run, isReady: () => ready };
})();