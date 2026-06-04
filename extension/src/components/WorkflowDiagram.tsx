import React, { useEffect, useId, useRef, useState } from "react";

interface WorkflowDiagramProps {
  definition: string;
}

export const WorkflowDiagram: React.FC<WorkflowDiagramProps> = ({ definition }) => {
  const id = useId().replace(/:/g, "");
  const [svg, setSvg] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [scale, setScale] = useState(1);
  const [offset, setOffset] = useState({ x: 0, y: 0 });
  const dragRef = useRef<{ pointerId: number; startX: number; startY: number; originX: number; originY: number } | null>(null);

  useEffect(() => {
    let cancelled = false;
    setSvg("");
    setError(null);

    import("mermaid")
      .then((module) => {
        const mermaid = module.default;
        mermaid.initialize({
          startOnLoad: false,
          securityLevel: "strict",
          theme: "base",
          themeVariables: {
            primaryColor: "#eef2ff",
            primaryTextColor: "#0f172a",
            primaryBorderColor: "#6366f1",
            lineColor: "#64748b",
            secondaryColor: "#f8fafc",
            tertiaryColor: "#ffffff",
            fontFamily: "Inter, -apple-system, BlinkMacSystemFont, sans-serif",
          },
        });
        return mermaid.render(`workflow-${id}`, definition);
      })
      .then(({ svg }) => {
        if (!cancelled) {
          setSvg(svg.replace("<svg", '<svg class="workflow-svg"'));
        }
      })
      .catch((err) => {
        if (!cancelled) setError(err instanceof Error ? err.message : "처리 경로를 렌더링할 수 없습니다.");
      });

    return () => {
      cancelled = true;
    };
  }, [definition, id]);

  if (error) {
    return <div className="workflow-error">{error}</div>;
  }

  if (!svg) {
    return <div className="workflow-loading">처리 경로를 그리는 중...</div>;
  }

  const resetView = () => {
    setScale(1);
    setOffset({ x: 0, y: 0 });
  };

  return (
    <div className="workflow-diagram">
      <div className="workflow-toolbar">
        <button type="button" onClick={() => setScale((value) => Math.max(0.5, value - 0.15))}>축소</button>
        <span>{Math.round(scale * 100)}%</span>
        <button type="button" onClick={() => setScale((value) => Math.min(2.4, value + 0.15))}>확대</button>
        <button type="button" onClick={resetView}>원점</button>
      </div>
      <div
        className="workflow-pan-stage"
        onPointerDown={(event) => {
          event.currentTarget.setPointerCapture(event.pointerId);
          dragRef.current = {
            pointerId: event.pointerId,
            startX: event.clientX,
            startY: event.clientY,
            originX: offset.x,
            originY: offset.y,
          };
        }}
        onPointerMove={(event) => {
          const drag = dragRef.current;
          if (!drag || drag.pointerId !== event.pointerId) return;
          setOffset({
            x: drag.originX + event.clientX - drag.startX,
            y: drag.originY + event.clientY - drag.startY,
          });
        }}
        onPointerUp={(event) => {
          if (dragRef.current?.pointerId === event.pointerId) {
            dragRef.current = null;
          }
        }}
        onPointerCancel={() => {
          dragRef.current = null;
        }}
        onWheel={(event) => {
          if (!event.ctrlKey && !event.metaKey) return;
          event.preventDefault();
          const direction = event.deltaY > 0 ? -0.1 : 0.1;
          setScale((value) => Math.min(2.4, Math.max(0.5, value + direction)));
        }}
      >
        <div
          className="workflow-pan-content"
          style={{ transform: `translate(${offset.x}px, ${offset.y}px) scale(${scale})` }}
          dangerouslySetInnerHTML={{ __html: svg }}
        />
      </div>
    </div>
  );
};
