import { ConsoleApp } from "./ConsoleApp";
import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "AXIO Console",
  description:
    "AXIO local-first AI workspace.",
};

export default function Home() {
  return <ConsoleApp />;
}
