import { createSeedDatabase, type Database } from './fixtures'

/**
 * The mock persistence layer — the whole of it.
 *
 * Seeded from fixtures on first run, then kept in localStorage. That means a
 * project created during a demo is still there after a refresh, which is the
 * only thing separating a convincing prototype from a brittle one.
 *
 * When a real backend arrives this file is deleted outright: api/*.ts stops
 * calling getDb()/commit() and calls fetch() instead. Nothing above the api
 * layer knows this exists.
 */

const STORAGE_KEY = 'nozom.db.v1'

let cache: Database | null = null

function persist(): void {
  if (!cache) return
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(cache))
  } catch {
    // Quota exceeded or storage disabled (private browsing). The in-memory
    // cache still works for this session — losing persistence is not fatal.
  }
}

/** Reads the database, seeding it on first call. */
export function getDb(): Database {
  if (cache) return cache

  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (raw) {
      const parsed = JSON.parse(raw) as Partial<Database>
      const seed = createSeedDatabase()
      // Merge over a fresh seed so a stored snapshot from an older build,
      // missing a collection added since, cannot crash the app.
      cache = { ...seed, ...parsed }
      return cache
    }
  } catch {
    // Corrupted JSON — fall through and reseed rather than leave the app broken.
  }

  cache = createSeedDatabase()
  persist()
  return cache
}

/**
 * Applies a mutation and saves. Every write in the api layer goes through here,
 * so persistence is impossible to forget.
 */
export function commit<T>(mutate: (db: Database) => T): T {
  const db = getDb()
  const result = mutate(db)
  persist()
  return result
}

/** Restores the seed data — wired to "reset demo data" in Settings. */
export function resetDb(): void {
  cache = createSeedDatabase()
  persist()
}

/** Deep-copies a record on the way out so callers cannot mutate the store by reference. */
export function clone<T>(value: T): T {
  return structuredClone(value)
}
