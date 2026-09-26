import { Placeholder } from "../placeholder/Placeholder";

/** Login (artboard 6.1) is the first F2 screen; until then the route exists so the auth guard has a target. */
export function LoginRoute() {
  return <Placeholder titleKey="login.title" />;
}
