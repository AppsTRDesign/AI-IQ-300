// The look of Mermaid diagrams in AI IQ 300: soft accent nodes, pill edge labels, thin grey lines, light and dark.
// One source for the chat (Diagram.jsx) and for PNG/SVG files the render_diagram tool writes (the backend reads this
// file and runs it in a headless page), so a downloaded picture looks like the one in the chat.
// Plain JavaScript, no imports: it must also run as a classic script.
export function diagramTheme(dark, font) {
  const c = dark
    ? { node: "#1d2a44", border: "#3a5a99", text: "#dbe6ff", line: "#6b7280", bg: "#26262b", soft: "#22324f", second: "#2a2340", third: "#1f3a33", note: "#3a3320", noteText: "#f5e7b8", muted: "#a1a1aa" }
    : { node: "#eef4ff", border: "#b9cff7", text: "#1e3a6e", line: "#a1a1aa", bg: "#ffffff", soft: "#f5f8ff", second: "#f3efff", third: "#ecfbf3", note: "#fff8e1", noteText: "#5b4a12", muted: "#52525b" };
  const themeVariables = {
    darkMode: dark, background: "transparent", fontFamily: font, fontSize: "13px",
    primaryColor: c.node, primaryBorderColor: c.border, primaryTextColor: c.text,
    secondaryColor: c.second, secondaryBorderColor: c.border, secondaryTextColor: c.text,
    tertiaryColor: c.third, tertiaryBorderColor: c.border, tertiaryTextColor: c.text,
    lineColor: c.line, textColor: c.text, mainBkg: c.node, nodeBorder: c.border, clusterBkg: c.soft,
    clusterBorder: c.border, titleColor: c.text, edgeLabelBackground: c.bg, nodeTextColor: c.text,
    noteBkgColor: c.note, noteTextColor: c.noteText, noteBorderColor: c.border,
    actorBkg: c.node, actorBorder: c.border, actorTextColor: c.text, actorLineColor: c.line,
    signalColor: c.line, signalTextColor: c.text, labelBoxBkgColor: c.node, labelBoxBorderColor: c.border,
    labelTextColor: c.text, loopTextColor: c.text, activationBkgColor: c.soft, activationBorderColor: c.border,
    sectionBkgColor: c.soft, altSectionBkgColor: c.bg, taskBkgColor: c.node, taskBorderColor: c.border,
    taskTextColor: c.text, taskTextLightColor: c.text, taskTextOutsideColor: c.text, activeTaskBkgColor: c.second,
    doneTaskBkgColor: c.third, critBkgColor: dark ? "#4a1f24" : "#fde8e8", critBorderColor: dark ? "#b45360" : "#f3a3a3",
    gridColor: dark ? "#2f2f35" : "#e4e4e7", todayLineColor: dark ? "#4f8cff" : "#2563eb",
    pie1: dark ? "#4f8cff" : "#2563eb", pie2: dark ? "#a78bfa" : "#7c3aed", pie3: dark ? "#34d399" : "#059669",
    pie4: dark ? "#fbbf24" : "#d97706", pie5: dark ? "#f87171" : "#dc2626", pie6: dark ? "#22d3ee" : "#0891b2",
    pieStrokeColor: c.bg, pieOuterStrokeColor: c.border, pieTitleTextColor: c.text, pieLegendTextColor: c.text,
  };
  // Rounded nodes, dashed decision shapes, pill edge labels, soft node shadow: the look of the chat's own cards.
  const themeCSS = `
    .node rect, .node path, .node polygon, .node circle { stroke-width: 1px; }
    .node rect { rx: 10px; ry: 10px; }
    .node polygon { stroke-dasharray: 4 3; }
    .node .label, .nodeLabel { font-weight: 600; font-size: 12.5px; }
    .flowchart-link, .edgePath .path, .relation, .transition { stroke-width: 1.2px; }
    .edgeLabel, .edgeLabel p, .edgeLabel span { background: transparent !important; }
    .edgeLabel .labelBkg, foreignObject .edgeLabel { background: transparent !important; }
    .edgeLabel p { padding: 0; border: 0; }
    span.edgeLabel:has(p:not(:empty)), span.edgeLabel:not(:has(p)):not(:empty) {
      display: inline-block; padding: 1px 9px; border-radius: 999px; font-size: 11.5px; font-weight: 500;
      background: ${c.bg} !important; border: 1px solid ${c.border}; color: ${c.text};
    }
    .cluster rect { rx: 14px; ry: 14px; stroke-dasharray: 5 4; }
    .cluster-label .nodeLabel, .cluster span { font-weight: 700; color: ${c.muted}; }
    .node { filter: drop-shadow(0 1px 1.5px rgb(0 0 0 / ${dark ? 0.35 : 0.06})); }
  `;
  return { themeVariables, themeCSS };
}

// The Mermaid settings both renderers use. forExport: labels as SVG text (a canvas can paint it; HTML labels
// taint the canvas) - the headless renderer keeps HTML labels, it screenshots the page instead.
export function diagramConfig(dark, font, forExport) {
  const { themeVariables, themeCSS } = diagramTheme(dark, font);
  const plain = { useMaxWidth: false };
  return {
    startOnLoad: false, securityLevel: "strict", theme: "base", themeVariables, themeCSS, fontFamily: font,
    htmlLabels: !forExport, suppressErrorRendering: true,
    flowchart: { curve: "basis", htmlLabels: !forExport, padding: 14, nodeSpacing: 42, rankSpacing: 50, useMaxWidth: false, diagramPadding: 12 },
    sequence: { useMaxWidth: false, mirrorActors: false, boxMargin: 8, messageFontWeight: 500 },
    gantt: plain, journey: plain, class: plain, state: plain, er: plain, pie: plain, mindmap: plain, timeline: plain,
    gitGraph: plain,
  };
}
