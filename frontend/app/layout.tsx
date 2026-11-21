import "./globals.css";
import { Instrument_Serif, JetBrains_Mono, Inter_Tight } from "next/font/google";

const serif = Instrument_Serif({ weight: "400", subsets: ["latin"], variable: "--font-serif" });
const mono = JetBrains_Mono({ subsets: ["latin"], variable: "--font-mono-face" });
const sans = Inter_Tight({ subsets: ["latin"], variable: "--font-sans-face" });

export const metadata = { title: "ATHLETE IQ", description: "Your performance has patterns. We find them." };

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`${serif.variable} ${mono.variable} ${sans.variable}`}>
      <body>{children}</body>
    </html>
  );
}
