// A resolved Promise only yields to microtasks; use a new task so the native
// view, input events and GIF player get time between bounded CPU batches.
export const yieldToUI = () => new Promise(resolve => setTimeout(resolve, 0))
