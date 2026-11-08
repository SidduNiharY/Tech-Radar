// Ambient types for React and Next.js when node_modules is not yet scaffolded
declare namespace React {
  export type ReactNode = any;
  export type FC<P = {}> = (props: P) => any;
  export type ComponentType<P = {}> = (props: P) => any;
  export function useState<T>(initial: T | (() => T)): [T, (value: T | ((prev: T) => T)) => void];
  export function useEffect(effect: () => void | (() => void), deps?: readonly any[]): void;
  export function useRef<T>(initial?: T): { current: T };
  export function useMemo<T>(factory: () => T, deps: readonly any[]): T;
  export function useCallback<T extends (...args: any[]) => any>(callback: T, deps: readonly any[]): T;
  export function useId(): string;
  export type KeyboardEvent<T = any> = any;
  export type ChangeEvent<T = any> = any;
  export type FormEvent<T = any> = any;
  export type MouseEvent<T = any> = any;

  export namespace JSX {
    export type Element = any;
  }
}

declare module "react" {
  export = React;
}

declare module "react/jsx-runtime" {
  export const jsx: any;
  export const jsxs: any;
  export const Fragment: any;
}

declare namespace JSX {
  interface Element extends React.ReactNode {}
  interface IntrinsicElements {
    [elemName: string]: any;
  }
  interface IntrinsicAttributes {
    key?: any;
    ref?: any;
  }
}
