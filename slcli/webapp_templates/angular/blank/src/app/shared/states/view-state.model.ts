export interface ViewState<T> {
  value: T | null;
  isLoading: boolean;
  error: string | null;
}

export function createEmptyViewState<T>(): ViewState<T> {
  return {
    value: null,
    isLoading: false,
    error: null,
  };
}
