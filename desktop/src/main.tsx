import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
// HashRouter (not BrowserRouter): Electron serves the app from file:// in
// production, where path-based history routing does not work.
import { HashRouter, Route, Routes } from "react-router";
import { App } from "@/app";
import { NotFound } from "@/pages/not-found";
import { RouteProvider } from "@/providers/router-provider";
import { ThemeProvider } from "@/providers/theme-provider";
import "@/styles/globals.css";

createRoot(document.getElementById("root")!).render(
    <StrictMode>
        <ThemeProvider defaultTheme="dark">
            <HashRouter>
                <RouteProvider>
                    <Routes>
                        <Route path="/" element={<App />} />
                        <Route path="*" element={<NotFound />} />
                    </Routes>
                </RouteProvider>
            </HashRouter>
        </ThemeProvider>
    </StrictMode>,
);
