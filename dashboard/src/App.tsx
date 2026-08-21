import React from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, NavLink, Route, Routes } from "react-router-dom";
import Overview from "./pages/Overview";
import Mail from "./pages/Mail";
import Identity from "./pages/Identity";
import Clients from "./pages/Clients";
import Edge from "./pages/Edge";
import Workloads from "./pages/Workloads";

const queryClient = new QueryClient();

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <div className="shell">
          <nav className="side">
            <div className="brand">Cronnecture</div>
            <NavLink to="/" end className={({ isActive }) => (isActive ? "active" : "")}>
              Overview
            </NavLink>
            <NavLink to="/mail" className={({ isActive }) => (isActive ? "active" : "")}>
              Mail
            </NavLink>
            <NavLink to="/identity" className={({ isActive }) => (isActive ? "active" : "")}>
              Identity
            </NavLink>
            <NavLink to="/clients" className={({ isActive }) => (isActive ? "active" : "")}>
              Clients
            </NavLink>
            <NavLink to="/edge" className={({ isActive }) => (isActive ? "active" : "")}>
              Edge
            </NavLink>
            <NavLink to="/workloads" className={({ isActive }) => (isActive ? "active" : "")}>
              Workloads
            </NavLink>
          </nav>
          <main className="page">
            <Routes>
              <Route path="/" element={<Overview />} />
              <Route path="/mail" element={<Mail />} />
              <Route path="/identity" element={<Identity />} />
              <Route path="/clients" element={<Clients />} />
              <Route path="/edge" element={<Edge />} />
              <Route path="/workloads" element={<Workloads />} />
            </Routes>
          </main>
        </div>
      </BrowserRouter>
    </QueryClientProvider>
  );
}
