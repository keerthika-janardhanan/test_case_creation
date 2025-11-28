export type NodeStatus = 'hidden' | 'revealed' | 'active' | 'completed' | 'processing';

export type NodeType = 'start' | 'choice' | 'action' | 'process' | 'end';

export interface FlowNodeData {
  id: string;
  type: NodeType;
  label: string;
  description?: string;
  status: NodeStatus;
  progress?: number; // 0-100 for processing nodes
  icon?: React.ReactNode;
  color?: string;
  position: { x: number; y: number };
  layer: number; // 0-2, for parallax depth (0=background, 2=foreground)
  parentId?: string;
  children?: string[];
  onAction?: () => void | Promise<void>;
  metadata?: Record<string, any>;
  flowType?: 'recorder' | 'execute' | 'neutral'; // For connection direction
}

export interface ConnectionData {
  id: string;
  fromNodeId: string;
  toNodeId: string;
  direction: 'left' | 'right'; // Flow direction for animation
  status: 'inactive' | 'active' | 'completed';
  flowType: 'recorder' | 'execute' | 'neutral';
}

export interface PopupData {
  nodeId: string;
  title: string;
  fields: PopupField[];
  onSubmit: (values: Record<string, any>) => void | Promise<void>;
  onCancel: () => void;
}

export interface PopupField {
  name: string;
  label: string;
  type: 'text' | 'number' | 'file' | 'textarea' | 'select';
  placeholder?: string;
  required?: boolean;
  options?: { value: string; label: string }[];
}
