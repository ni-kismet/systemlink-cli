using System.ComponentModel;
using System.ComponentModel.DataAnnotations;

namespace NationalInstruments.CommandLine.WorkflowCLI.Models
{
    /// <summary>
    /// Defines a state for a workflow.
    /// </summary>
    public class WorkflowState
    {
        /// <summary>
        /// The name of the state.
        /// </summary>]
        /// <example>NEW</example>
        [Required]
        required public TestPlanState Name { get; set; }

        /// <summary>
        /// Whether or not the test plan dashboard is available for the state.
        /// </summary>
        [DefaultValue(false)]
        public bool DashboardAvailable { get; set; } = false;

        /// <summary>
        /// The default substate associated with the state.
        /// </summary>
        [Required]
        [StringLength(100, MinimumLength = 1)]
        required public string DefaultSubstate { get; set; }

        /// <summary>
        /// The substates associated with the state.
        /// </summary>
        [Required]
        [MaxLength(length: 100)]
        required public IReadOnlyCollection<WorkflowSubstate> Substates { get; set; }
    }
}
