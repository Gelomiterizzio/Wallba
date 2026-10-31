import { useState } from "react"
import { Link } from "react-router-dom"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { useAuthedApi } from "../../app/session"
import { ErrorPanel, LoadingState, PageHeader } from "../../components/states"

const STORAGE = "wallba.guard.project"

type Entry = {
  path: string
  name: string
  kind: string
  risk: string
  reasons: string[]
  posture: string | null
  preventive: boolean
}

type Summary = {
  project: { id: string; display_name: string; canonical_root: string }
  files_scanned: number
  directories_scanned: number
  by_risk: Record<string, number>
}

export function ProtectionPage() {
  const { client } = useAuthedApi()
  const queryClient = useQueryClient()
  const [projectId, setProjectId] = useState<string | null>(() => sessionStorage.getItem(STORAGE))
  const [rootPath, setRootPath] = useState("")
  const [directory, setDirectory] = useState("")
  const [selected, setSelected] = useState<string[]>([])
  const [posture, setPosture] = useState("alert")
  const [notice, setNotice] = useState<string | null>(null)

  const summary = useQuery({
    queryKey: ["guard", "summary", projectId],
    enabled: projectId != null,
    queryFn: ({ signal }) => client.get<Summary>(`/guard/projects/${projectId}/summary`, undefined, signal),
  })
  const listing = useQuery({
    queryKey: ["guard", "children", projectId, directory],
    enabled: projectId != null,
    queryFn: ({ signal }) =>
      client.get<{ entries: Entry[] }>(`/guard/projects/${projectId}/children`, { path: directory }, signal),
  })

  function remember(id: string) {
    sessionStorage.setItem(STORAGE, id)
    setProjectId(id)
    setSelected([])
    setDirectory("")
    void queryClient.invalidateQueries({ queryKey: ["guard"] })
  }

  const open = useMutation({
    mutationFn: () => client.post<Summary>("/guard/projects", { root_path: rootPath }),
    onSuccess: (data) => remember(data.project.id),
  })
  const sample = useMutation({
    mutationFn: () => client.post<Summary>("/guard/samples"),
    onSuccess: (data) => {
      setNotice("Se abrió el proyecto sintético. Los valores de ejemplo no son credenciales.")
      remember(data.project.id)
    },
  })
  const protect = useMutation({
    mutationFn: async () => {
      const entries = listing.data?.entries ?? []
      for (const path of selected) {
        const entry = entries.find((item) => item.path === path)
        if (!entry || projectId == null) {
          continue
        }
        await client.post(`/guard/projects/${projectId}/rules`, {
          relative_path: entry.path,
          kind: entry.kind === "directory" ? "directory" : "file",
          posture,
        })
      }
    },
    onSuccess: async () => {
      setNotice("Política guardada para la selección.")
      setSelected([])
      await queryClient.invalidateQueries({ queryKey: ["guard"] })
    },
  })

  function toggle(path: string) {
    setSelected((current) => (current.includes(path) ? current.filter((item) => item !== path) : [...current, path]))
  }

  return (
    <>
      <PageHeader
        title="Protección"
        description="El análisis usa nombres y rutas. El bloqueo preventivo solo cubre al agente de prueba de WALLBA."
      />
      <form
        className="panel"
        onSubmit={(event) => {
          event.preventDefault()
          open.mutate()
        }}
      >
        <div className="field">
          <label htmlFor="project-root">Carpeta del proyecto</label>
          <input id="project-root" value={rootPath} onChange={(event) => setRootPath(event.target.value)} />
        </div>
        <div className="row">
          <button type="submit" className="button button-primary" disabled={open.isPending || rootPath.length === 0}>
            Analizar carpeta
          </button>
          <button type="button" className="button" disabled={sample.isPending} onClick={() => sample.mutate()}>
            Abrir proyecto sintético
          </button>
        </div>
      </form>
      {open.isError ? <ErrorPanel error={open.error} /> : null}
      {sample.isError ? <ErrorPanel error={sample.error} /> : null}
      {notice ? <p aria-live="polite">{notice}</p> : null}
      {summary.data ? (
        <p className="meta">
          {summary.data.project.display_name}: {summary.data.files_scanned} archivos, {summary.data.directories_scanned}{" "}
          carpetas, {summary.data.by_risk.CRITICAL ?? 0} críticos. <Link to="/alerts">Alertas</Link>
        </p>
      ) : null}
      {listing.isPending && projectId ? <LoadingState label="Cargando carpetas" /> : null}
      {listing.data ? (
        <div className="panel">
          <div className="row">
            <label htmlFor="guard-posture">Política para la selección</label>
            <select id="guard-posture" value={posture} onChange={(event) => setPosture(event.target.value)}>
              <option value="monitor">Monitorear (no bloquea)</option>
              <option value="alert">Alertar (no bloquea)</option>
              <option value="block_read">Bloquear lecturas del agente de prueba</option>
              <option value="block_write">Bloquear escrituras del agente de prueba</option>
              <option value="block_all">Bloquear lectura y escritura del agente de prueba</option>
            </select>
            <button type="button" className="button button-primary" disabled={selected.length === 0 || protect.isPending} onClick={() => protect.mutate()}>
              Proteger selección ({selected.length})
            </button>
          </div>
          {directory ? (
            <button type="button" className="button" onClick={() => setDirectory(directory.includes("/") ? directory.slice(0, directory.lastIndexOf("/")) : "")}>
              Subir
            </button>
          ) : null}
          <ul className="timeline">
            {listing.data.entries.map((entry) => (
              <li key={entry.path}>
                <label className="check-field">
                  <input type="checkbox" checked={selected.includes(entry.path)} onChange={() => toggle(entry.path)} />
                  {entry.kind === "directory" ? (
                    <button type="button" className="button" onClick={() => setDirectory(entry.path)}>
                      {entry.name}
                    </button>
                  ) : (
                    <span className="mono">{entry.name}</span>
                  )}
                  <span className="badge badge-neutral">{entry.risk}</span>
                  <span className="meta">{entry.posture ?? "sin política"}{entry.preventive ? " · preventiva para lectura" : ""}</span>
                </label>
                <p className="meta">{entry.reasons[0]}</p>
              </li>
            ))}
          </ul>
          {listing.data.entries.length === 0 ? <p>Esta carpeta no tiene elementos visibles.</p> : null}
        </div>
      ) : null}
      {protect.isError ? <ErrorPanel error={protect.error} /> : null}
    </>
  )
}
