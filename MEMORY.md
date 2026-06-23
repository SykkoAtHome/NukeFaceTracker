# Projekt NukeFaceTracker - Pamięć i Zasady (MEMORY)

## Architektura i Konwencje
- **Wizualizacja vs Źródło Prawdy**: Węzeł NoOp dla Blendshapes wygenerowany w Nuke (z zapiętymi klatkami kluczowymi) to wyłącznie wygodna wizualizacja dla użytkownika. Prawdziwym źródłem prawdy (source of truth) dla deformacji siatki lub wewnątrz innych operacji backendowych pozostaje zawsze plik `.blendshapes.json` (sidecar).
- **GPU Delegate w MediaPipe**: W skrypcie śledzącym `tracker_backend.py` nie wolno włączać flagi `Delegate.GPU` jeśli włączone jest wsparcie dla blendshapes (`output_face_blendshapes=True`). Istnieje znany błąd w bibliotece MediaPipe (bug #5576), który całkowicie "psuje" i psuje wyniki wydobywania deformatorów mimiki z użyciem GPU na niektórych środowiskach. Do czasu załatania przez Google, blendshapes wymuszają ekstrakcję na CPU.
- **Układ Portów Multi-Input (Etap 2)**:
  - Port 0: `Source_Face` (główne wejście obrazu).
  - Port 1: `SmartVector` (refinement). Do NOT change this port assignment, as vector channel resolving and refinement logic are strictly bound to it.
  - Port 2: `Expression_Face` (wejście referencyjne mimiki).
  Port 2 (`Expression_Face`) jest pomijany podczas automatycznego przeszukiwania drzewa upstream (`find_upstream_read`), zapobiegając wyciekom ścieżek śledzenia.

