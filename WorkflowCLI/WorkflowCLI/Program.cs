using System.CommandLine;
using NationalInstruments.CommandLine.WorkflowCLI.Extensions;
using NationalInstruments.CommandLine.WorkflowCLI.Utilities;

namespace NationalInstruments.CommandLine.WorkflowCLI
{
    internal class Program
    {
        public static async Task<int> Main(string[] args)
        {
            var inputOption = new Option<string>(
                name: "--input",
                description: "Path to the workflow JSON file")
                { IsRequired = true };

            var outputOption = new Option<string>(
                name: "--output",
                description: "Path to the output SVG or PNG file",
                getDefaultValue: () => "output.svg");

            var rootCommand = new RootCommand("Workflow JSON to Mermaid Diagram Generator")
            {
                inputOption,
                outputOption
            };

            rootCommand.SetHandler(
                ((string input, string output) =>
                {
                    string workflowJson = FileOperations.ReadAll(input);
                    if (string.IsNullOrEmpty(workflowJson))
                    {
                        Console.WriteLine("Error: Workflow JSON is empty or invalid.");
                        return;
                    }

                    var workflow = JsonOperations.DeserializeWorkflow(workflowJson);
                    if (workflow == null)
                    {
                        Console.WriteLine("Error: Failed to deserialize workflow.");
                        return;
                    }

                    var result = workflow?.TransformToMermaid();
                    Console.WriteLine("Generated Mermaid code:");
                    Console.WriteLine(result);

                    MermaidCLI.GenerateImage(result, output);
                    MermaidCLI.OpenImage(output);
                }), inputOption,
                outputOption);

            return await rootCommand.InvokeAsync(args);
        }
    }
}
