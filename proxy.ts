import { NextResponse, type NextRequest } from "next/server"
import { LOGIN_PATH, SESSION_COOKIE_NAME, loginUrl } from "@/lib/auth"

/**
 * Optimistic check only: no session cookie means "not signed in", so go to the login page
 * before rendering anything. The cookie is not verified here; the FastAPI backend checks
 * it on every /api request, which is the real protection.
 */
export function proxy(request: NextRequest) {
  const { pathname, search } = request.nextUrl
  if (pathname === LOGIN_PATH || request.cookies.has(SESSION_COOKIE_NAME)) {
    return NextResponse.next()
  }
  return NextResponse.redirect(new URL(loginUrl(pathname + search), request.url))
}

export const config = {
  // Pages only: not the /api proxy to FastAPI, Next.js internals, or files like /aig-logo.png.
  matcher: ["/((?!api/|_next/static|_next/image|favicon\\.ico|.*\\.[A-Za-z0-9]+$).*)"],
}
