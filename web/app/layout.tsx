import type { Metadata } from "next";
import { Archivo, Syne } from "next/font/google";
import { Nav } from "./nav";
import "./globals.css";

export const metadata: Metadata = { title: "sortie" };

const syne = Syne({
  subsets: ["latin"],
  weight: ["600", "700", "800"],
  variable: "--font-syne",
});

const archivo = Archivo({
  subsets: ["latin"],
  weight: ["400", "500", "600", "700"],
  variable: "--font-archivo",
});

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`${syne.variable} ${archivo.variable}`}>
      <body className="min-h-screen bg-green font-sans text-snow antialiased">
        <div className="mx-auto max-w-[1040px] px-[22px] pb-24">
          <header className="pt-8 pb-5">
            <span className="font-display text-4xl font-extrabold tracking-tight text-orange">
              sortie
            </span>
          </header>
          <div className="sprocket" />
          <Nav />
          {children}
        </div>
      </body>
    </html>
  );
}
