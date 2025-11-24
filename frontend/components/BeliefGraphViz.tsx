"use client";

import { useEffect, useRef, useState } from "react";
import { BeliefNode, BeliefEdge } from "@/lib/api-client";

interface BeliefGraphVizProps {
  nodes: BeliefNode[];
  edges: BeliefEdge[];
  onNodeClick?: (node: BeliefNode) => void;
}

interface GraphNode {
  id: string;
  x: number;
  y: number;
  vx: number;
  vy: number;
  data: BeliefNode;
}

interface GraphEdge {
  source: string;
  target: string;
  data: BeliefEdge;
}

export function BeliefGraphViz({ nodes, edges, onNodeClick }: BeliefGraphVizProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [graphNodes, setGraphNodes] = useState<GraphNode[]>([]);
  const [graphEdges, setGraphEdges] = useState<GraphEdge[]>([]);
  const [selectedNode, setSelectedNode] = useState<GraphNode | null>(null);
  const animationRef = useRef<number | undefined>(undefined);

  // Initialize graph data - runs on mount and when nodes/edges change
  useEffect(() => {
    const width = 800;
    const height = 600;

    if (nodes.length === 0) {
      return;
    }

    // Create nodes with random initial positions
    const newNodes: GraphNode[] = nodes.map((node) => ({
      id: node.id,
      x: Math.random() * width,
      y: Math.random() * height,
      vx: 0,
      vy: 0,
      data: node,
    }));

    const newEdges: GraphEdge[] = edges.map((edge) => ({
      source: edge.source_id,
      target: edge.target_id,
      data: edge,
    }));

    setGraphNodes(newNodes);
    setGraphEdges(newEdges);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [nodes, edges]);

  // Simple force simulation
  useEffect(() => {
    if (!canvasRef.current || graphNodes.length === 0) return;

    const canvas = canvasRef.current;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const width = canvas.width;
    const height = canvas.height;

    const simulate = () => {
      // Apply forces
      const newNodes = graphNodes.map((node) => {
        let fx = 0;
        let fy = 0;

        // Repulsion from other nodes
        graphNodes.forEach((other) => {
          if (node.id === other.id) return;
          const dx = node.x - other.x;
          const dy = node.y - other.y;
          const dist = Math.sqrt(dx * dx + dy * dy) || 1;
          const force = 100 / (dist * dist);
          fx += (dx / dist) * force;
          fy += (dy / dist) * force;
        });

        // Attraction along edges
        graphEdges.forEach((edge) => {
          let other: GraphNode | undefined;
          let sign = 1;

          if (edge.source === node.id) {
            other = graphNodes.find((n) => n.id === edge.target);
          } else if (edge.target === node.id) {
            other = graphNodes.find((n) => n.id === edge.source);
            sign = -1;
          }

          if (other) {
            const dx = other.x - node.x;
            const dy = other.y - node.y;
            const dist = Math.sqrt(dx * dx + dy * dy) || 1;
            const force = dist * 0.001;
            fx += (dx / dist) * force * sign;
            fy += (dy / dist) * force * sign;
          }
        });

        // Center gravity
        fx += (width / 2 - node.x) * 0.0001;
        fy += (height / 2 - node.y) * 0.0001;

        // Update velocity and position
        const damping = 0.85;
        const newVx = (node.vx + fx) * damping;
        const newVy = (node.vy + fy) * damping;
        const newX = Math.max(30, Math.min(width - 30, node.x + newVx));
        const newY = Math.max(30, Math.min(height - 30, node.y + newVy));

        return { ...node, vx: newVx, vy: newVy, x: newX, y: newY };
      });

      setGraphNodes(newNodes);

      // Render
      ctx.clearRect(0, 0, width, height);

      // Draw edges
      graphEdges.forEach((edge) => {
        const source = newNodes.find((n) => n.id === edge.source);
        const target = newNodes.find((n) => n.id === edge.target);
        if (!source || !target) return;

        ctx.beginPath();
        ctx.moveTo(source.x, source.y);
        ctx.lineTo(target.x, target.y);
        ctx.strokeStyle = edge.data.relation === "supports" ? "#10b981" : edge.data.relation === "contradicts" ? "#ef4444" : "#6b7280";
        ctx.lineWidth = 1;
        ctx.stroke();
      });

      // Draw nodes
      newNodes.forEach((node) => {
        const radius = 10 + (node.data.confidence || 0.5) * 15;
        const confidence = node.data.confidence || 0.5;
        const hue = confidence * 120; // 0=red, 120=green

        ctx.beginPath();
        ctx.arc(node.x, node.y, radius, 0, 2 * Math.PI);
        ctx.fillStyle = `hsl(${hue}, 70%, 50%)`;
        ctx.fill();
        ctx.strokeStyle = selectedNode?.id === node.id ? "#000" : "#fff";
        ctx.lineWidth = selectedNode?.id === node.id ? 3 : 1;
        ctx.stroke();

        // Label
        ctx.fillStyle = "#000";
        ctx.font = "10px sans-serif";
        ctx.textAlign = "center";
        ctx.fillText(
          node.data.title.substring(0, 15),
          node.x,
          node.y + radius + 12
        );
      });

      animationRef.current = requestAnimationFrame(simulate);
    };

    animationRef.current = requestAnimationFrame(simulate);

    return () => {
      if (animationRef.current) {
        cancelAnimationFrame(animationRef.current);
      }
    };
  }, [graphNodes, graphEdges, selectedNode]);

  const handleCanvasClick = (e: React.MouseEvent<HTMLCanvasElement>) => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const rect = canvas.getBoundingClientRect();
    const x = e.clientX - rect.left;
    const y = e.clientY - rect.top;

    // Find clicked node
    const clicked = graphNodes.find((node) => {
      const radius = 10 + (node.data.confidence || 0.5) * 15;
      const dx = node.x - x;
      const dy = node.y - y;
      return Math.sqrt(dx * dx + dy * dy) <= radius;
    });

    if (clicked) {
      setSelectedNode(clicked);
      if (onNodeClick) {
        onNodeClick(clicked.data);
      }
    } else {
      setSelectedNode(null);
    }
  };

  return (
    <div>
      <canvas
        ref={canvasRef}
        width={800}
        height={600}
        onClick={handleCanvasClick}
        className="border border-[var(--border)] rounded cursor-pointer bg-white shadow-soft"
      />
      <div className="mt-4 flex items-center gap-6 text-sm text-[var(--text-secondary)]">
        <div className="flex items-center gap-2">
          <div className="w-4 h-0.5 bg-green-500"></div>
          <span>Supports</span>
        </div>
        <div className="flex items-center gap-2">
          <div className="w-4 h-0.5 bg-red-500"></div>
          <span>Contradicts</span>
        </div>
        <div className="flex items-center gap-2">
          <div className="w-4 h-0.5 bg-gray-500"></div>
          <span>Depends on</span>
        </div>
        <div className="ml-auto">Node size and color indicate confidence level</div>
      </div>
    </div>
  );
}
