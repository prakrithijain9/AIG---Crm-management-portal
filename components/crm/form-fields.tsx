"use client"

import type { ReactNode } from "react"
import { cn } from "@/lib/utils"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"

type FieldProps = {
  label: string
  children: ReactNode
  error?: string
}

export function Field({ label, children, error }: FieldProps) {
  return (
    // min-w-0 lets the field shrink to its grid column instead of overflowing into the next one.
    <div className="grid min-w-0 gap-2">
      <Label>{label}</Label>
      {children}
      {error ? (
        <p role="alert" className="text-xs text-destructive">
          {error}
        </p>
      ) : null}
    </div>
  )
}

type TextFieldProps = {
  label: string
  value: string
  onChange: (value: string) => void
  placeholder?: string
  type?: string
  required?: boolean
  error?: string
}

export function TextField({
  label,
  value,
  onChange,
  placeholder,
  type = "text",
  required,
  error,
}: TextFieldProps) {
  return (
    <Field label={label} error={error}>
      <Input
        type={type}
        value={value}
        required={required}
        placeholder={placeholder}
        aria-invalid={error ? true : undefined}
        onChange={(event) => onChange(event.target.value)}
      />
    </Field>
  )
}

type SelectFieldProps = {
  label?: string
  value: string
  onChange: (value: string) => void
  options: { value: string; label: string }[]
  placeholder?: string
  className?: string
  error?: string
}

export function SelectField({
  label,
  value,
  onChange,
  options,
  placeholder,
  className,
  error,
}: SelectFieldProps) {
  const select = (
    // `items` tells Base UI each option's label; without it the trigger shows the raw value (e.g. a UUID).
    <Select
      items={options}
      value={value}
      onValueChange={(next) => onChange(String(next))}
    >
      <SelectTrigger
        className={cn("min-w-0", className ?? "w-full")}
        aria-invalid={error ? true : undefined}
      >
        <SelectValue className="min-w-0">
          {(selected: string) => (
            <span className="truncate">
              {options.find((option) => option.value === selected)?.label ??
                placeholder}
            </span>
          )}
        </SelectValue>
      </SelectTrigger>
      <SelectContent>
        {options.map((option) => (
          <SelectItem key={option.value} value={option.value}>
            {option.label}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  )

  if (!label) return select

  return (
    <Field label={label} error={error}>
      {select}
    </Field>
  )
}

export function DetailList({
  items,
}: {
  items: { label: string; value: ReactNode }[]
}) {
  return (
    <dl className="grid gap-3">
      {items.map((item) => (
        <div key={item.label} className="grid gap-1">
          <dt className="text-xs font-medium tracking-wide text-muted-foreground uppercase">
            {item.label}
          </dt>
          <dd className="text-sm">{item.value}</dd>
        </div>
      ))}
    </dl>
  )
}
