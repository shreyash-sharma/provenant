export type NodeType = "MODULE" | "FILE" | "SYMBOL";
export type EdgeType = "import" | "recent" | "vulnerability";

export interface GraphNode {
  id: string;
  name: string;
  type: NodeType;
  path?: string;
  riskScore?: number;
  description?: string;
}

export interface GraphEdge {
  source: string;
  target: string;
  type: EdgeType;
  weight?: number;
}
