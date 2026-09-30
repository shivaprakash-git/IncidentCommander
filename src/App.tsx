import React from "react";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { IncidentProvider } from "./context/IncidentContext";
import { AppShell } from "./components/Sidebar";
import { LandingPage } from "./pages/LandingPage";
import { DashboardPage } from "./pages/DashboardPage";
import { IncidentsPage } from "./pages/IncidentsPage";
import { PredictorListPage } from "./pages/PredictorListPage";
import { PredictorPanelPage } from "./pages/PredictorPanelPage";
import { IncidentDetailPage } from "./pages/IncidentDetailPage";
import { TimelineTab } from "./pages/tabs/TimelineTab";
import { RcaTab } from "./pages/tabs/RcaTab";
import { ActionsTab } from "./pages/tabs/ActionsTab";
import { ComparisonTab } from "./pages/tabs/ComparisonTab";
import { AuditTrailPage } from "./pages/AuditTrailPage";
import { SumlogUploadPage } from "./pages/SumlogUploadPage";

export const App: React.FC = () => {
  return (
    <IncidentProvider>
      <BrowserRouter>
        <Routes>
          <Route path="/" element={<LandingPage />} />
          <Route element={<AppShell />}>
            <Route path="/dashboard" element={<DashboardPage />} />
            <Route path="/incidents" element={<IncidentsPage />} />
            <Route path="/incidents/:id" element={<IncidentDetailPage />}>
              <Route index element={<Navigate to="timeline" replace />} />
              <Route path="timeline" element={<TimelineTab />} />
              <Route path="rca" element={<RcaTab />} />
              <Route path="actions" element={<ActionsTab />} />
              <Route path="comparison" element={<ComparisonTab />} />
            </Route>
            <Route path="/predictor" element={<PredictorListPage />} />
            <Route path="/predictor/:patternId" element={<PredictorPanelPage />} />
            <Route path="/sumlog" element={<SumlogUploadPage />} />
            <Route path="/audit" element={<AuditTrailPage />} />
          </Route>
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </BrowserRouter>
    </IncidentProvider>
  );
};

export default App;
