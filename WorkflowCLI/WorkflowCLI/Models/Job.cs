namespace NationalInstruments.CommandLine.WorkflowCLI.Models
{
    /// <summary>
    /// Defines a Systems Management Job to be executed by a test plan job execution.
    /// </summary>
    public sealed class Job
    {
        /// <summary>
        /// The list of Salt job functions to execute.
        /// </summary>
        public IList<string> Functions { get; set; } = new List<string>();

        /// <summary>
        /// The list of argument lists to pass to each function.
        /// </summary>
        public IList<IList<object>> Arguments { get; set; } = new List<IList<object>>();

        /// <summary>
        /// Systems Management Job metadata. `queued` will be ignored.
        /// </summary>
        public IDictionary<string, object> Metadata { get; set; } = new Dictionary<string, object>();
    }
}
