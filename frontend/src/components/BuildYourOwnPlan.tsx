import { Link, useLocation } from "react-router-dom";
import { useBindingContext } from "../binding/Bound";
import { useYourPlan } from "../editor/YourPlanContext";
import { YOUR_PLAN } from "../editor/yourPlan";

/**
 * The foot-of-screen pointer to the plan editor, for a wide screen showing a named scenario. It is a plain link to the
 * Plan screen with the editor chosen: nothing of the editor is fetched until that choice is made there.
 */
export function BuildYourOwnPlan() {
  const yourPlan = useYourPlan();
  const { scenario } = useBindingContext();
  return yourPlan?.desktop && scenario !== YOUR_PLAN ? <Line /> : null;
}

// Apart so that a screen mounted without the app's router (its own tests) never reaches the router's hooks.
function Line() {
  const { search } = useLocation();
  const params = new URLSearchParams(search);
  params.set("scenario", YOUR_PLAN);
  return (
    <p className="text-sm text-slate-600" data-testid="build-your-own">
      Want to try your own hires and programs?{" "}
      <Link to={{ pathname: "/plan", search: `?${params}` }} className="font-medium text-ft-brand underline">
        Build your own plan
      </Link>
      .
    </p>
  );
}
