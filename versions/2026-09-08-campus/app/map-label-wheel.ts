/** Labels remain clickable DOM buttons. Forward only their wheel input through
 * the canvas's existing controls and pan-cancellation path, with unchanged
 * coordinates, wheel units and modifiers. Other panels retain native scrolling.
 */
export function connectMapLabelWheel(labels: HTMLElement, canvas: HTMLCanvasElement) {
  const forward = (event: WheelEvent) => {
    const wheel = new WheelEvent('wheel', {
      cancelable: true,
      bubbles: false,
      deltaX: event.deltaX,
      deltaY: event.deltaY,
      deltaZ: event.deltaZ,
      deltaMode: event.deltaMode,
      clientX: event.clientX,
      clientY: event.clientY,
      screenX: event.screenX,
      screenY: event.screenY,
      ctrlKey: event.ctrlKey,
      shiftKey: event.shiftKey,
      altKey: event.altKey,
      metaKey: event.metaKey,
      buttons: event.buttons,
    });
    canvas.dispatchEvent(wheel);
    if (wheel.defaultPrevented) {
      event.preventDefault();
      event.stopPropagation();
    }
  };
  labels.addEventListener('wheel', forward, { passive: false });
  return () => labels.removeEventListener('wheel', forward);
}
