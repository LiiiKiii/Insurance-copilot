import type { Metadata, Viewport } from "next"
import { Outfit, DM_Sans } from "next/font/google"
import "./globals.css"
import { LocaleProvider } from "@/lib/i18n"

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  maximumScale: 5,
  viewportFit: "cover",
}

const outfit = Outfit({
  variable: "--font-outfit",
  subsets: ["latin"],
  display: "swap",
})

const dmSans = DM_Sans({
  variable: "--font-dm-sans",
  subsets: ["latin"],
  display: "swap",
})

// SSR fallback only; LocaleProvider rewrites document.title client-side
// based on the persisted locale (see web/src/lib/i18n/LocaleProvider.tsx).
export const metadata: Metadata = {
  title: "Insurance Copilot | Business Advisory",
  description: "Insurance business advisory platform",
}

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode
}>) {
  return (
    <html lang="en" suppressHydrationWarning>
      <head>
        <script
          dangerouslySetInnerHTML={{
            __html: `(function(){var t=localStorage.getItem('theme');if(t==='dark'||(!t&&window.matchMedia('(prefers-color-scheme:dark)').matches)){document.documentElement.classList.add('dark')}})()`,
          }}
        />
      </head>
      <body
        className={`${outfit.variable} ${dmSans.variable} font-sans antialiased`}
      >
        <LocaleProvider>{children}</LocaleProvider>
      </body>
    </html>
  )
}
