const fs = require("fs");

const inputPath = process.argv[2] || "sbom.cdx.json";
const bom = JSON.parse(fs.readFileSync(inputPath, "utf8"));

function collectComponentRefs(component, refs) {
  if (component["bom-ref"]) {
    refs.add(component["bom-ref"]);
  }

  for (const child of component.components || []) {
    collectComponentRefs(child, refs);
  }
}

function collectDevelopmentRefs(components, refs) {
  for (const component of components || []) {
    const isDevelopment =
      (component.properties || []).some(
        (property) =>
          property.name === "cdx:npm:package:development" && property.value === "true",
      );

    if (isDevelopment) {
      collectComponentRefs(component, refs);
    } else {
      collectDevelopmentRefs(component.components, refs);
    }
  }
}

function filterComponents(components, refs) {
  return (components || [])
    .filter((component) => !refs.has(component["bom-ref"]))
    .map((component) => ({
      ...component,
      ...(component.components
        ? { components: filterComponents(component.components, refs) }
        : {}),
    }));
}

const developmentRefs = new Set();
collectDevelopmentRefs(bom.components, developmentRefs);

bom.components = filterComponents(bom.components, developmentRefs);
bom.dependencies = (bom.dependencies || [])
  .filter((dependency) => !developmentRefs.has(dependency.ref))
  .map((dependency) => ({
    ...dependency,
    dependsOn: (dependency.dependsOn || []).filter((ref) => !developmentRefs.has(ref)),
  }));

fs.writeFileSync(inputPath, `${JSON.stringify(bom, null, 2)}\n`);