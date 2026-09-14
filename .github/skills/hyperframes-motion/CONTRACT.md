# Motion Contract

The skill owns the authoring method and bounded CLI adapter. HyperFrames owns browser playback,
sampling and encoding. Node, HyperFrames, parse5 and media binaries resolve only from the supplied
external runtime. No dependency/cache/output is written into the skill.

`configuration(root, runtime)` requires distinct existing absolute roots outside the skill.
`containedPath` rejects traversal and escaping symlinks. `composition(html, parse)` uses parse5
to require one direct-body CSS composition with declared start, dimensions and finite duration.
`parseAtTimestamps` enforces unsigned decimals, increasing order, at most twenty samples, all
strictly inside the duration. Maximum duration is eight seconds; dimensions are at most 4096.

`validate` accepts only version, doctor, lint, check, render and explicitly authorized browser
setup shapes. `runAllowed` validates before spawning HyperFrames, closes stdin and bounds runtime.
Render requires explicit approval; the runner never exposes template download, installation of
arbitrary assets, bundle/export, publication or cloud commands.

CSS-only local composition is the supported subset. Scripts, event handlers and nested browsing
contexts are refused. Referenced local assets and CSS still need review; markup checks are not an
OS sandbox or a complete CSS security parser. Use a restricted runtime for untrusted inputs.
Stored output and actual decoded frames, not CLI acknowledgement, establish render success.