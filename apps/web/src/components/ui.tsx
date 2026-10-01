import {
  forwardRef,
  useId,
  useRef,
  type ButtonHTMLAttributes,
  type InputHTMLAttributes,
  type ReactNode,
  type SelectHTMLAttributes,
} from "react";
import { createPortal } from "react-dom";
import { useTranslation } from "react-i18next";
import { AlertTriangle, Info, RotateCcw, X } from "lucide-react";
import { cn } from "@/lib/utils";
import { useDialogBehavior } from "@/lib/hooks";

type Tone = "neutral" | "pos" | "neg" | "warn" | "brand";

// ── Layout ──────────────────────────────────────────────────────────────

export const PageHeader = ({
  title,
  subtitle,
  actions,
  badge,
}: {
  title: ReactNode;
  subtitle?: ReactNode;
  actions?: ReactNode;
  badge?: ReactNode;
}) => (
  <header className="flex flex-wrap items-end justify-between gap-x-6 gap-y-3">
    <div className="min-w-0">
      <div className="flex flex-wrap items-center gap-2">
        <h1 className="text-2xl font-semibold tracking-tight text-ink">{title}</h1>
        {badge}
      </div>
      {subtitle && <p className="mt-1 max-w-[65ch] text-sm text-muted">{subtitle}</p>}
    </div>
    {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
  </header>
);

export const Card = ({
  children,
  className,
  as: Tag = "div",
}: {
  children: ReactNode;
  className?: string;
  as?: "div" | "section" | "article";
}) => <Tag className={cn("card p-5", className)}>{children}</Tag>;

export const SectionTitle = ({
  children,
  right,
  id,
}: {
  children: ReactNode;
  right?: ReactNode;
  id?: string;
}) => (
  <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
    <h2 id={id} className="text-base font-semibold text-ink">
      {children}
    </h2>
    {right}
  </div>
);

// ── Controls ────────────────────────────────────────────────────────────

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: "primary" | "secondary" | "outline" | "ghost" | "danger";
  size?: "sm" | "md";
}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(
  ({ variant = "primary", size = "md", className, type = "button", ...props }, ref) => (
    <button
      ref={ref}
      type={type}
      className={cn(
        variant === "primary" && "btn-primary",
        (variant === "secondary" || variant === "outline") && "btn-secondary",
        variant === "ghost" && "btn-ghost",
        variant === "danger" && "btn-danger",
        size === "sm" && "min-h-9 px-3 py-1.5 text-sm",
        className,
      )}
      {...props}
    />
  ),
);
Button.displayName = "Button";

/** Icon-only button: `label` is required so it always has an accessible name. */
export const IconButton = forwardRef<
  HTMLButtonElement,
  Omit<ButtonProps, "children" | "aria-label"> & { label: string; icon: ReactNode }
>(({ label, icon, variant = "ghost", className, ...props }, ref) => (
  <Button
    ref={ref}
    variant={variant}
    aria-label={label}
    title={label}
    className={cn("size-10 min-h-10 shrink-0 p-0", className)}
    {...props}
  >
    {icon}
  </Button>
));
IconButton.displayName = "IconButton";

export const Input = forwardRef<HTMLInputElement, InputHTMLAttributes<HTMLInputElement>>(
  ({ className, ...props }, ref) => <input ref={ref} className={cn("input", className)} {...props} />,
);
Input.displayName = "Input";

export const Select = ({ children, className, ...props }: SelectHTMLAttributes<HTMLSelectElement>) => (
  <select className={cn("input cursor-pointer pe-8", className)} {...props}>
    {children}
  </select>
);

/** Label above, control, then hint or error below. The <label> wraps the control for association. */
export const Field = ({
  label,
  hint,
  error,
  children,
  className,
}: {
  label: ReactNode;
  hint?: ReactNode;
  error?: ReactNode;
  children: ReactNode;
  className?: string;
}) => (
  <div className={cn("space-y-1.5", className)}>
    <label className="block space-y-1.5">
      <span className="label">{label}</span>
      {children}
    </label>
    {error ? (
      <p role="alert" className="text-sm text-neg">
        {error}
      </p>
    ) : (
      hint && <p className="text-sm text-muted">{hint}</p>
    )}
  </div>
);

export function Segmented<T extends string | number>({
  options,
  value,
  onChange,
  label,
  className,
}: {
  options: { value: T; label: ReactNode }[];
  value: T;
  onChange: (v: T) => void;
  label: string;
  className?: string;
}) {
  return (
    <div
      role="radiogroup"
      aria-label={label}
      className={cn("inline-flex flex-wrap gap-1 rounded-lg bg-sunken p-1", className)}
    >
      {options.map((o) => {
        const active = o.value === value;
        return (
          <button
            key={String(o.value)}
            type="button"
            role="radio"
            aria-checked={active}
            onClick={() => onChange(o.value)}
            className={cn(
              "min-h-9 rounded-md px-3 text-sm font-medium transition-colors",
              active ? "bg-raised text-ink shadow-card" : "text-muted hover:text-ink",
            )}
          >
            {o.label}
          </button>
        );
      })}
    </div>
  );
}

// ── Display ─────────────────────────────────────────────────────────────

const toneText: Record<Tone, string> = {
  neutral: "bg-sunken text-muted",
  pos: "bg-pos/10 text-pos",
  neg: "bg-neg/10 text-neg",
  warn: "bg-warn/10 text-warn",
  brand: "bg-brand/10 text-brand",
};

export const Badge = ({ tone = "neutral", children }: { tone?: Tone; children: ReactNode }) => (
  <span className={cn("chip", toneText[tone])}>{children}</span>
);

export const StatTile = ({
  label,
  value,
  tone,
  icon,
  hint,
  className,
}: {
  label: ReactNode;
  value: ReactNode;
  tone?: "pos" | "neg" | "brand";
  icon?: ReactNode;
  hint?: ReactNode;
  className?: string;
}) => (
  <div className={cn("card flex flex-col gap-2 p-4", className)}>
    <div className="flex items-center justify-between gap-2 text-muted">
      <p className="text-sm font-medium">{label}</p>
      {icon && <span aria-hidden>{icon}</span>}
    </div>
    <p
      className={cn(
        "text-2xl font-semibold tracking-tight",
        tone === "pos" && "text-pos",
        tone === "neg" && "text-neg",
        tone === "brand" && "text-brand",
      )}
    >
      {value}
    </p>
    {hint && <p className="text-sm text-muted">{hint}</p>}
  </div>
);

/** Horizontal meter (budgets, goals, limits). Text beside it carries the value; colour is secondary. */
export const Meter = ({
  value,
  tone = "brand",
  label,
  className,
}: {
  value: number;
  tone?: "brand" | "pos" | "warn" | "neg";
  label: string;
  className?: string;
}) => {
  const pct = Math.max(0, Math.min(100, value));
  return (
    <div
      role="meter"
      aria-label={label}
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={Math.round(value)}
      className={cn("h-2 overflow-hidden rounded-full bg-line", className)}
    >
      <div
        className={cn(
          "h-full rounded-full transition-[width] duration-300 ease-out",
          tone === "brand" && "bg-brand",
          tone === "pos" && "bg-pos",
          tone === "warn" && "bg-warn",
          tone === "neg" && "bg-neg",
        )}
        style={{ width: `${pct}%` }}
      />
    </div>
  );
};

export const Notice = ({
  tone = "brand",
  children,
  onDismiss,
  className,
}: {
  tone?: Tone;
  children: ReactNode;
  onDismiss?: () => void;
  className?: string;
}) => {
  const { t } = useTranslation();
  const Icon = tone === "neg" || tone === "warn" ? AlertTriangle : Info;
  return (
    <div
      role={tone === "neg" ? "alert" : "status"}
      className={cn("flex items-start gap-3 rounded-lg px-3.5 py-3 text-sm", toneText[tone], className)}
    >
      <Icon size={16} className="mt-0.5 shrink-0" aria-hidden />
      <div className="min-w-0 flex-1 text-ink">{children}</div>
      {onDismiss && (
        <button
          type="button"
          onClick={onDismiss}
          aria-label={t("common.dismiss")}
          className="-m-1 rounded p-1 text-muted hover:text-ink"
        >
          <X size={16} />
        </button>
      )}
    </div>
  );
};

export const Table = ({ children, label }: { children: ReactNode; label: string }) => (
  <div className="-mx-5 overflow-x-auto">
    <table
      aria-label={label}
      className={cn(
        "w-full min-w-full text-sm",
        "[&_th]:px-5 [&_th]:py-2.5 [&_th]:text-start [&_th]:text-xs [&_th]:font-medium [&_th]:text-muted",
        "[&_thead]:border-b [&_thead]:border-line [&_thead]:bg-sunken/60",
        "[&_td]:px-5 [&_td]:py-3 [&_tbody_tr]:border-b [&_tbody_tr]:border-line last:[&_tbody_tr]:border-0",
      )}
    >
      {children}
    </table>
  </div>
);

// ── States ──────────────────────────────────────────────────────────────

export const Spinner = ({ label }: { label?: string }) => (
  <div role="status" className="flex items-center justify-center gap-3 py-12 text-muted">
    <span className="size-5 animate-spin rounded-full border-2 border-line border-t-brand" aria-hidden />
    {label}
  </div>
);

export const Skeleton = ({ className }: { className?: string }) => (
  <div aria-hidden className={cn("relative overflow-hidden rounded-lg bg-sunken", className)}>
    <div className="absolute inset-0 -translate-x-full animate-shimmer bg-gradient-to-r from-transparent via-raised/60 to-transparent" />
  </div>
);

/** Page-shaped loading placeholder: header, stat row, one content block. */
export const PageSkeleton = ({ tiles = 4 }: { tiles?: number }) => {
  const { t } = useTranslation();
  return (
    <div role="status" aria-label={t("common.loading")} className="space-y-6">
      <Skeleton className="h-8 w-56" />
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        {Array.from({ length: tiles }, (_, i) => (
          <Skeleton key={i} className="h-24" />
        ))}
      </div>
      <Skeleton className="h-64" />
    </div>
  );
};

export const EmptyState = ({
  icon,
  title,
  body,
  action,
}: {
  icon?: ReactNode;
  title: ReactNode;
  body?: ReactNode;
  action?: ReactNode;
}) => (
  <div className="flex flex-col items-center px-6 py-12 text-center">
    {icon && (
      <div className="mb-4 grid size-12 place-items-center rounded-xl bg-brand/10 text-brand" aria-hidden>
        {icon}
      </div>
    )}
    <p className="text-base font-semibold text-ink">{title}</p>
    {body && <p className="mt-1 max-w-md text-sm text-muted">{body}</p>}
    {action && <div className="mt-5">{action}</div>}
  </div>
);

export const ErrorState = ({ onRetry, message }: { onRetry?: () => void; message?: ReactNode }) => {
  const { t } = useTranslation();
  return (
    <div role="alert" className="card flex flex-col items-center px-6 py-10 text-center">
      <div className="mb-3 grid size-11 place-items-center rounded-xl bg-neg/10 text-neg" aria-hidden>
        <AlertTriangle size={20} />
      </div>
      <p className="font-semibold text-ink">{t("common.errorTitle")}</p>
      <p className="mt-1 max-w-md text-sm text-muted">{message ?? t("common.errorBody")}</p>
      {onRetry && (
        <Button variant="secondary" size="sm" className="mt-4" onClick={onRetry}>
          <RotateCcw size={14} aria-hidden /> {t("common.retry")}
        </Button>
      )}
    </div>
  );
};

/** Chart wrapper: fixed height (no layout shift) plus a text summary for screen readers. */
export const ChartFrame = ({
  summary,
  height = "h-64",
  children,
}: {
  summary: string;
  height?: string;
  children: ReactNode;
}) => (
  <figure className="m-0">
    <div className={height} aria-hidden>
      {children}
    </div>
    <figcaption className="sr-only">{summary}</figcaption>
  </figure>
);

// ── Dialog ──────────────────────────────────────────────────────────────

/** Accessible dialog: bottom sheet under sm, centred card above. Esc, focus trap, focus return. */
export const Modal = ({
  open,
  onClose,
  title,
  children,
  size = "md",
}: {
  open: boolean;
  onClose: () => void;
  title: string;
  children: ReactNode;
  size?: "md" | "lg";
}) => {
  const { t } = useTranslation();
  const ref = useRef<HTMLDivElement>(null);
  const titleId = useId();
  useDialogBehavior(ref, open, onClose);
  if (!open) return null;
  return createPortal(
    <div className="fixed inset-0 z-50 flex items-end justify-center sm:items-center sm:p-4">
      <div className="absolute inset-0 bg-ink/40 backdrop-blur-[2px]" onClick={onClose} aria-hidden />
      <div
        ref={ref}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        tabIndex={-1}
        className={cn(
          "relative z-10 flex max-h-[90dvh] w-full flex-col rounded-t-2xl border border-line bg-raised shadow-pop",
          "animate-fadeUp pb-safe sm:rounded-2xl sm:pb-0",
          size === "md" ? "sm:max-w-md" : "sm:max-w-2xl",
        )}
      >
        <div className="flex items-center justify-between gap-3 border-b border-line px-5 py-3.5">
          <h2 id={titleId} className="text-lg font-semibold text-ink">
            {title}
          </h2>
          <IconButton label={t("common.close")} icon={<X size={18} />} onClick={onClose} className="-me-2" />
        </div>
        <div className="overflow-y-auto px-5 py-4">{children}</div>
      </div>
    </div>,
    document.body,
  );
};
