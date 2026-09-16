import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

// ponytail: http basic auth, swap for a real login screen if this ever has more than one user
export function middleware(req: NextRequest) {
  const expected = process.env.SORTIE_PASSWORD;
  if (!expected) {
    return new NextResponse("SORTIE_PASSWORD is not set", { status: 500 });
  }

  const header = req.headers.get("authorization") ?? "";
  if (header.startsWith("Basic ")) {
    const decoded = atob(header.slice(6));
    const password = decoded.slice(decoded.indexOf(":") + 1);
    if (password === expected) return NextResponse.next();
  }

  return new NextResponse("Not authorised", {
    status: 401,
    headers: { "WWW-Authenticate": 'Basic realm="sortie"' },
  });
}

export const config = { matcher: ["/((?!_next/static|_next/image|favicon.ico).*)"] };
