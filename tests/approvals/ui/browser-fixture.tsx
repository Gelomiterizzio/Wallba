/** Isolated fixture surface, never used by the production feature. */
import { createRoot } from "react-dom/client"
import { ApprovalCenter } from "../../../frontend/src/features/approvals/ApprovalCenter"

createRoot(document.getElementById("root")!).render(<main>
  <p style={{ background: "#fcd34d", color: "#0b1120", padding: "12px 24px", margin: 0, fontFamily: "system-ui", fontWeight: 700 }}>
    DATOS DE PRUEBA · Harness aislado de Persona 3 · No es el dashboard de Persona 4
  </p>
  <ApprovalCenter />
</main>)
