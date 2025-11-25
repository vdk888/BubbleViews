import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Bubble - Sign In",
  description: "Sign in to Bubble Dashboard",
};

export default function LoginLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return children;
}
