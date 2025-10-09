const { Project } = require("ts-morph");
const path = require("path");
const fs = require("fs");

const repoPath = path.resolve(process.argv[2]);
const outputPath = path.resolve(process.argv[3]);

const project = new Project({
    tsConfigFilePath: path.join(repoPath, "tsconfig.json"),
    skipAddingFilesFromTsConfig: true
});

// Recursively add only src / relevant folders
function addSourceFiles(dir) {
    const entries = fs.readdirSync(dir, { withFileTypes: true });
    for (const entry of entries) {
        const fullPath = path.join(dir, entry.name);
        if (entry.isDirectory()) {
            if (["node_modules", ".git", "dist"].includes(entry.name)) continue;
            addSourceFiles(fullPath);
        } else if (fullPath.endsWith(".ts") || fullPath.endsWith(".tsx")) {
            project.addSourceFileAtPath(fullPath);
        }
    }
}

addSourceFiles(repoPath);

const parsedModules = project.getSourceFiles().map(sf => ({
    name: path.basename(sf.getFilePath()),
    path: sf.getFilePath(),
    functions: sf.getFunctions().map(f => f.getName()),
    classes: sf.getClasses().map(c => c.getName())
}));

fs.writeFileSync(outputPath, JSON.stringify({ modules: parsedModules }, null, 2));
console.log("Parsed TS repo scaffold written to", outputPath);
