/* eslint-disable no-unused-vars */
import type React from 'react';

declare module '*' {
  const value: React.ComponentType<any>;
  export default value;
  export const api: any;
  export const authStore: any;
}

declare module '*' {
  export const api: any;
  export const authStore: {
    setSession: (user: unknown) => void;
    clear: () => void;
  };
  const value: any;
  export default value;
}

