using System.Text.Json;
using NationalInstruments.CommandLine.WorkflowCLI.Models;
using NationalInstruments.SystemLink.ServiceBase;

namespace NationalInstruments.CommandLine.WorkflowCLI.Utilities
{
    public static class JsonOperations
    {
        public static Workflow? DeserializeWorkflow(string workflowJson)
        {
            var options = new System.Text.Json.JsonSerializerOptions
            {
                PropertyNameCaseInsensitive = true,
                WriteIndented = true,
                Converters =
            {
                new JsonStringEnumMemberConverter(JsonNamingPolicy.SnakeCaseUpper)
            }
            };
            return System.Text.Json.JsonSerializer.Deserialize<Workflow>(workflowJson, options);
        }
    }
}
