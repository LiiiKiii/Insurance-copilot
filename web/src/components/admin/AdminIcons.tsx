interface IconProps {
  className?: string
  size?: number
}

function Icon({ children, className, size = 18 }: IconProps & { children: React.ReactNode }) {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
      aria-hidden="true"
    >
      {children}
    </svg>
  )
}

export function DatabaseIcon(props: IconProps) {
  return <Icon {...props}><ellipse cx="12" cy="5" rx="9" ry="3" /><path d="M3 5v14c0 1.66 4 3 9 3s9-1.34 9-3V5" /><path d="M3 12c0 1.66 4 3 9 3s9-1.34 9-3" /></Icon>
}

export function FileTextIcon(props: IconProps) {
  return <Icon {...props}><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" /><polyline points="14 2 14 8 20 8" /><line x1="8" y1="13" x2="16" y2="13" /><line x1="8" y1="17" x2="16" y2="17" /></Icon>
}

export function PlusIcon(props: IconProps) {
  return <Icon {...props}><line x1="12" y1="5" x2="12" y2="19" /><line x1="5" y1="12" x2="19" y2="12" /></Icon>
}

export function TrashIcon(props: IconProps) {
  return <Icon {...props}><polyline points="3 6 5 6 21 6" /><path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6" /><path d="M10 11v6M14 11v6M9 6V4h6v2" /></Icon>
}

export function XIcon(props: IconProps) {
  return <Icon {...props}><line x1="18" y1="6" x2="6" y2="18" /><line x1="6" y1="6" x2="18" y2="18" /></Icon>
}

export function ChevronLeftIcon(props: IconProps) {
  return <Icon {...props}><polyline points="15 18 9 12 15 6" /></Icon>
}

export function ChevronRightIcon(props: IconProps) {
  return <Icon {...props}><polyline points="9 18 15 12 9 6" /></Icon>
}

export function EyeIcon(props: IconProps) {
  return <Icon {...props}><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z" /><circle cx="12" cy="12" r="3" /></Icon>
}

export function EyeOffIcon(props: IconProps) {
  return <Icon {...props}><path d="M17.94 17.94A10.1 10.1 0 0 1 12 20c-7 0-11-8-11-8a18.5 18.5 0 0 1 5.06-5.94M9.9 4.24A9.1 9.1 0 0 1 12 4c7 0 11 8 11 8a18.6 18.6 0 0 1-2.16 3.19" /><line x1="1" y1="1" x2="23" y2="23" /></Icon>
}

export function LogOutIcon(props: IconProps) {
  return <Icon {...props}><path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4" /><polyline points="16 17 21 12 16 7" /><line x1="21" y1="12" x2="9" y2="12" /></Icon>
}

export function SpinnerIcon({ className, ...props }: IconProps) {
  return <Icon {...props} className={`animate-spin ${className ?? ''}`}><path d="M21 12a9 9 0 1 1-6.219-8.56" /></Icon>
}
