import { StatusPill } from "./StatusPill";
import { StripeDivider } from "./StripeDivider";

export function NavBar({ onMenu, menuOpen }: { onMenu: () => void; menuOpen: boolean }) {
  return (
    <header className="shrink-0 bg-canvas">
      <div className="flex h-16 w-full items-center justify-between px-4 sm:px-6">
        <div className="flex items-center gap-3">
          <button
            type="button"
            onClick={onMenu}
            aria-label="Open conversations"
            aria-expanded={menuOpen}
            aria-controls="conversations"
            className="-ml-2 flex size-12 flex-col items-center justify-center gap-1.5 md:hidden"
          >
            <span className="h-px w-5 bg-ink" />
            <span className="h-px w-5 bg-ink" />
            <span className="h-px w-5 bg-ink" />
          </button>
          <span aria-hidden className="flex gap-0.5">
            <span className="h-5 w-1 bg-m-blue-light" />
            <span className="h-5 w-1 bg-m-blue-dark" />
            <span className="h-5 w-1 bg-m-red" />
          </span>
          <span className="text-sm font-bold uppercase tracking-machined text-ink">Knowledge Assistant</span>
        </div>

        <StatusPill />
      </div>
      <StripeDivider />
      <div className="h-px bg-hairline-strong" />
    </header>
  );
}
