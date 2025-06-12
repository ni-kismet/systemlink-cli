namespace NationalInstruments.CommandLine.WorkflowCLI.Models
{
    public class Workflow
    {
        /// <summary>
        /// The array of actions defined for the workflow.
        /// </summary>
        required public IReadOnlyCollection<WorkflowAction> Actions { get; set; }

        /// <summary>
        /// The array of states defined for the workflow.
        /// </summary>
        required public IReadOnlyCollection<WorkflowState> States { get; set; }
    }
}
