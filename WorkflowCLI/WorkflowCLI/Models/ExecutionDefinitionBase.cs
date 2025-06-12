using System.ComponentModel.DataAnnotations;
using System.Text.Json.Serialization;

namespace NationalInstruments.CommandLine.WorkflowCLI.Models
{
    /// <summary>
    /// Defines an execution action for a test plan.
    /// </summary>
    /// Using JSON polymorphic deserialization attributes would be preferred to a custom JSON converter. However, the current
    /// implementation of polymorphic deserialization in System.Text.Json requires that the discriminator property be first
    /// in the JSON object. If it is not, it returns a NotSupportedException, which is not helpful to API users. This is a
    /// known issue and is being tracked by https://github.com/dotnet/runtime/issues/72604. It is expected to be fixed in .NET 9.
    public class ExecutionDefinitionBase
    {
        /// <summary>
        /// The action the execution definition implements.
        /// </summary>
        [Required]
        [StringLength(maximumLength: 128, MinimumLength = 1)]
        public string? Action { get; set; }

        /// <summary>
        /// The type of execution implementation.
        /// </summary>
        [Required]
        public ExecutionType? Type { get; set; }
    }

    /// <summary>
    /// Defines an unimplemented execution for a test plan. This type will not trigger an execution or transition the test plan state.
    /// </summary>
    public class NoneExecutionDefinition : ExecutionDefinitionBase
    {
        /// <summary>
        /// Constructor
        /// </summary>
        public NoneExecutionDefinition()
        {
            Type = ExecutionType.None;
        }
    }

    /// <summary>
    /// Defines a manual execution for a test plan. This type will not trigger an execution, but will
    /// transition the test plan state in accordance with the action.
    /// </summary>
    public class ManualExecutionDefinition : ExecutionDefinitionBase
    {
        /// <summary>
        /// Constructor.
        /// </summary>
        public ManualExecutionDefinition()
        {
            Type = ExecutionType.Manual;
        }
    }

    /// <summary>
    /// Defines a notebook execution for a test plan. This type will trigger a notebook execution, and
    /// transition the test plan state in accordance with the action.
    /// </summary>
    public class NotebookExecutionDefinition : ExecutionDefinitionBase
    {
        /// <summary>
        /// Constructor.
        /// </summary>
        public NotebookExecutionDefinition()
        {
            Type = ExecutionType.Notebook;
        }

        /// <summary>
        /// The ID of the notebook to execute.
        /// </summary>
        [Required]
        [JsonPropertyOrder(int.MaxValue - 1)]
        public string? NotebookId { get; set; }

        /// <summary>
        /// Dictionary of parameters that will be passed to the notebook when the execution is run.
        /// </summary>
        [JsonPropertyOrder(int.MaxValue)]
        public IDictionary<string, object> Parameters { get; set; } = new Dictionary<string, object>();
    }

    /// <summary>
    /// Defines a Systems Management Job execution for a test plan. This type will trigger a Jobs and
    /// transition the test plan state in accordance with the action.
    /// </summary>
    public sealed class JobExecutionDefinition : ExecutionDefinitionBase
    {
        /// <summary>
        /// Constructor
        /// </summary>
        public JobExecutionDefinition()
        {
            Type = ExecutionType.Job;
        }

        /// <summary>
        /// The list of jobs to execute. When the action is executed, all of the jobs will be queued.
        /// If creating any job fails, all jobs will be canceled. If a job fails during execution,
        /// subsequent jobs will still run.
        /// </summary>
        public IList<Job> Jobs { get; set; } = new List<Job>();

        /// <summary>
        /// The ID of the system to execute the jobs on instead of the system associated with the test plan.
        /// </summary>
        [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
        public string? SystemId { get; set; }
    }
}
