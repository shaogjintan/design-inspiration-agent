"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from "react";
import {
  DetectedRoom,
  HousingTypeId,
  ProjectState,
  RoomGeneration,
  RoomInspo,
  RoomRequirement,
  STORAGE_KEY,
  UploadedImage,
} from "@/lib/types";
import { MAX_ITERATIONS_PER_ROOM } from "@/lib/ai/bedrock";

const EMPTY_STATE: ProjectState = {
  projectName: "Untitled Project",
  housingType: null,
  floorPlanImage: null,
  overallColorScheme: null,
  overallStyleTheme: null,
  rooms: [],
  segmented: false,
  inspoByRoom: {},
  requirementsByRoom: {},
  generationsByRoom: {},
};

interface ProjectContextValue {
  project: ProjectState;
  ready: boolean;
  setProjectName: (name: string) => void;
  setHousingType: (id: HousingTypeId) => void;
  setFloorPlanImage: (image: UploadedImage | null) => void;
  setOverallStyle: (colorScheme: string | null, styleTheme: string | null) => void;
  setRooms: (rooms: DetectedRoom[]) => void;
  updateRoom: (roomId: string, patch: Partial<DetectedRoom>) => void;
  removeRoom: (roomId: string) => void;
  setSegmented: (v: boolean) => void;
  updateInspo: (roomId: string, patch: Partial<RoomInspo>) => void;
  updateRequirement: (roomId: string, patch: Partial<RoomRequirement>) => void;
  updateGeneration: (roomId: string, patch: Partial<RoomGeneration>) => void;
  resetProject: () => void;
}

const ProjectContext = createContext<ProjectContextValue | null>(null);

export function ProjectProvider({ children }: { children: React.ReactNode }) {
  const [project, setProject] = useState<ProjectState>(EMPTY_STATE);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    // One-time hydration from localStorage after mount (client-only storage,
    // so this can't be done during the initial render without a
    // server/client markup mismatch).
    try {
      const raw = window.localStorage.getItem(STORAGE_KEY);
      // eslint-disable-next-line react-hooks/set-state-in-effect
      if (raw) setProject({ ...EMPTY_STATE, ...JSON.parse(raw) });
    } catch {
      // ignore corrupt storage
    }
    setReady(true);
  }, []);

  useEffect(() => {
    if (!ready) return;
    try {
      window.localStorage.setItem(STORAGE_KEY, JSON.stringify(project));
    } catch {
      // storage full / unavailable — non-fatal for the demo
    }
  }, [project, ready]);

  const setProjectName = useCallback(
    (name: string) => setProject((p) => ({ ...p, projectName: name })),
    []
  );

  const setHousingType = useCallback(
    (id: HousingTypeId) =>
      setProject((p) => ({
        ...p,
        housingType: id,
        rooms: [],
        segmented: false,
        inspoByRoom: {},
        requirementsByRoom: {},
        generationsByRoom: {},
      })),
    []
  );

  const setFloorPlanImage = useCallback(
    (image: UploadedImage | null) =>
      setProject((p) => ({ ...p, floorPlanImage: image, segmented: false, rooms: [] })),
    []
  );

  const setOverallStyle = useCallback(
    (colorScheme: string | null, styleTheme: string | null) =>
      setProject((p) => ({
        ...p,
        overallColorScheme: colorScheme,
        overallStyleTheme: styleTheme,
      })),
    []
  );

  const setRooms = useCallback(
    (rooms: DetectedRoom[]) => setProject((p) => ({ ...p, rooms })),
    []
  );

  const updateRoom = useCallback(
    (roomId: string, patch: Partial<DetectedRoom>) =>
      setProject((p) => ({
        ...p,
        rooms: p.rooms.map((r) => (r.id === roomId ? { ...r, ...patch } : r)),
      })),
    []
  );

  const removeRoom = useCallback((roomId: string) => {
    setProject((p) => {
      const omit = <T,>(record: Record<string, T>): Record<string, T> =>
        Object.fromEntries(Object.entries(record).filter(([id]) => id !== roomId));
      const restInspo = omit(p.inspoByRoom);
      const restReq = omit(p.requirementsByRoom);
      const restGen = omit(p.generationsByRoom);
      return {
        ...p,
        rooms: p.rooms.filter((r) => r.id !== roomId),
        inspoByRoom: restInspo,
        requirementsByRoom: restReq,
        generationsByRoom: restGen,
      };
    });
  }, []);

  const setSegmented = useCallback(
    (v: boolean) => setProject((p) => ({ ...p, segmented: v })),
    []
  );

  const updateInspo = useCallback(
    (roomId: string, patch: Partial<RoomInspo>) =>
      setProject((p) => {
        const current: RoomInspo = p.inspoByRoom[roomId] ?? {
          roomId,
          images: [],
          colorScheme: p.overallColorScheme ?? "",
          styleTheme: p.overallStyleTheme ?? "",
        };
        return {
          ...p,
          inspoByRoom: {
            ...p.inspoByRoom,
            [roomId]: { ...current, ...patch },
          },
        };
      }),
    []
  );

  const updateRequirement = useCallback(
    (roomId: string, patch: Partial<RoomRequirement>) =>
      setProject((p) => {
        const current: RoomRequirement = p.requirementsByRoom[roomId] ?? {
          roomId,
          mustHaveItems: [],
          prompt: "",
        };
        return {
          ...p,
          requirementsByRoom: {
            ...p.requirementsByRoom,
            [roomId]: { ...current, ...patch },
          },
        };
      }),
    []
  );

  const updateGeneration = useCallback(
    (roomId: string, patch: Partial<RoomGeneration>) =>
      setProject((p) => {
        const current: RoomGeneration = p.generationsByRoom[roomId] ?? {
          roomId,
          iteration: 0,
          maxIterations: MAX_ITERATIONS_PER_ROOM,
          images: [],
          status: "idle",
        };
        return {
          ...p,
          generationsByRoom: {
            ...p.generationsByRoom,
            [roomId]: { ...current, ...patch },
          },
        };
      }),
    []
  );

  const resetProject = useCallback(() => {
    setProject(EMPTY_STATE);
    try {
      window.localStorage.removeItem(STORAGE_KEY);
    } catch {
      // ignore
    }
  }, []);

  const value = useMemo(
    () => ({
      project,
      ready,
      setProjectName,
      setHousingType,
      setFloorPlanImage,
      setOverallStyle,
      setRooms,
      updateRoom,
      removeRoom,
      setSegmented,
      updateInspo,
      updateRequirement,
      updateGeneration,
      resetProject,
    }),
    [
      project,
      ready,
      setProjectName,
      setHousingType,
      setFloorPlanImage,
      setOverallStyle,
      setRooms,
      updateRoom,
      removeRoom,
      setSegmented,
      updateInspo,
      updateRequirement,
      updateGeneration,
      resetProject,
    ]
  );

  return <ProjectContext.Provider value={value}>{children}</ProjectContext.Provider>;
}

export function useProject() {
  const ctx = useContext(ProjectContext);
  if (!ctx) throw new Error("useProject must be used within ProjectProvider");
  return ctx;
}
