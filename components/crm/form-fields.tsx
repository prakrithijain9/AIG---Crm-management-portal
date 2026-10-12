"use client"

import type { ReactNode } from "react"
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
    <div className="grid gap-2">
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
    <Select value={value} onValueChange={(next) => onChange(String(next))}>
      <SelectTrigger
        className={className ?? "w-full"}
        aria-invalid={error ? true : undefined}
      >
        <SelectValue placeholder={placeholder} />
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
