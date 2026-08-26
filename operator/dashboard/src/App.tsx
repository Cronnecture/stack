import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Route, Routes } from "react-router-dom";
import Shell from "./components/Shell";
import Overview from "./pages/Overview";
import Clients from "./pages/Clients";
import Client from "./pages/Client";
import Previews from "./pages/Previews";
import Jobs from "./pages/Jobs";
import Identity from "./pages/Identity";
import Mail from "./pages/Mail";
import Edge from "./pages/Edge";
import Cluster from "./pages/Cluster";

const queryClient = new QueryClient();

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <Routes>
          <Route element={<Shell />}>
            <Route path="/" element={<Overview />} />
            <Route path="/clients" element={<Clients />} />
            <Route path="/clients/:id" element={<Client />} />
            <Route path="/previews" element={<Previews />} />
            <Route path="/jobs" element={<Jobs />} />
            <Route path="/identity" element={<Identity />} />
            <Route path="/mail" element={<Mail />} />
            <Route path="/edge" element={<Edge />} />
            <Route path="/cluster" element={<Cluster />} />
          </Route>
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  );
}
