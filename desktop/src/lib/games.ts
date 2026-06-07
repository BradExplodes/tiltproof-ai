export interface GameInfo {
    id: string;
    name: string;
    thumbnail?: string;
    tagline: string;
}

export const GAME_CATALOG: Record<string, GameInfo> = {
    deadlock: {
        id: "deadlock",
        name: "Deadlock",
        thumbnail: "/games/deadlock.png",
        tagline: "6v6 action MOBA from Valve",
    },
    "league-of-legends": {
        id: "league-of-legends",
        name: "League of Legends",
        tagline: "Summoner's Rift coaching",
    },
    osu: {
        id: "osu",
        name: "osu!",
        tagline: "Rhythm aim and reading",
    },
    valorant: {
        id: "valorant",
        name: "VALORANT",
        tagline: "Tactical FPS rounds",
    },
};

export function getGameInfo(gameId: string): GameInfo {
    return (
        GAME_CATALOG[gameId] ?? {
            id: gameId,
            name: gameId.replace(/-/g, " ").replace(/\b\w/g, (c) => c.toUpperCase()),
            tagline: "Coaching available",
        }
    );
}
