import { forwardRef, type ButtonHTMLAttributes, type InputHTMLAttributes, type ReactNode } from "react";
import { motion } from "framer-motion";
import { cn } from "@/lib/utils";

export const Card = ({ children, className }: { children: ReactNode; className?: string }) => (
  <div className={cn("card p-5 animate-fadeUp", className)}>{children}</div>
);

export const SectionTitle = ({ children, right }: { children: ReactNode; right?: ReactNode }) => (
  <div className="mb-3 flex items-center justify-between">
    <h2 className="text-sm font-semibold uppercase tracking-wider text-muted">{children}</h2>
    {right}
  </div>
);

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: "primary" | "ghost" | "danger" | "outline";
  size?: "sm" | "md";
}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(
  ({ variant = "primary", size = "md", className, ...props }, ref) => (
    <button
      ref={ref}
      className={cn(
        variant === "primary" && "btn-primary",
        variant === "ghost" && "btn-ghost",
        variant === "outline" && "btn border-line hover:border-brand/50",
        variant === "danger" && "btn bg-neg text-white hover:bg-red-500",
        size === "sm" && "px-3 py-1.5 text-xs rounded-lg",
        className,
      )}
      {...props}
    />
  ),
);
Button.displayName = "Button";

export const Input = forwardRef<HTMLInputElement, InputHTMLAttributes<HTMLInputElement>>(
  ({ className, ...props }, ref) => <input ref={ref} className={cn("input", className)} {...props} />,
);
Input.displayName = "Input";

export const Select = ({
  children,
  className,
  ...props
}: React.SelectHTMLAttributes<HTMLSelectElement>) => (
  <select className={cn("input appearance-none pr-8", className)} {...props}>
    {children}
  </select>
);

export const Badge = ({
  tone = "neutral",
  children,
}: {
  tone?: "neutral" | "pos" | "neg" | "warn" | "brand";
  children: ReactNode;
}) => (
  <span
    className={cn(
      "chip",
      tone === "neutral" && "bg-muted/10 text-muted",
      tone === "pos" && "bg-pos/10 text-pos",
      tone === "neg" && "bg-neg/10 text-neg",
      tone === "warn" && "bg-amber-500/10 text-amber-500",
      tone === "brand" && "bg-brand/10 text-brand",
    )}
  >
    {children}
  </span>
);

export const Modal = ({
  open,
  onClose,
  title,
  children,
}: {
  open: boolean;
  onClose: () => void;
  title: string;
  children: ReactNode;
}) =>
  open ? (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div className="absolute inset-0 bg-black/40 backdrop-blur-sm" onClick={onClose} />
      <motion.div
        initial={{ opacity: 0, scale: 0.97 }}
        animate={{ opacity: 1, scale: 1 }}
        className="card relative z-10 w-full max-w-md p-6"
      >
        <h3 className="mb-4 text-lg font-semibold">{title}</h3>
        {children}
      </motion.div>
    </div>
  ) : null;

export const Spinner = ({ label }: { label?: string }) => (
  <div className="flex items-center justify-center gap-3 py-12 text-muted">
    <span className="size-5 animate-spin rounded-full border-2 border-line border-t-brand" />
    {label}
  </div>
);
