using System.ComponentModel.DataAnnotations;

namespace NationalInstruments.CommandLine.WorkflowCLI.Models
{
    /// <summary>
    /// Defines a substate for a state. Substates indicate the status or an intermediate state
    /// of the test plan resulting from actions taken during a top-level state.
    /// </summary>
    public class WorkflowSubstate
    {
        /// <summary>
        /// The name of the substate.
        /// </summary>
        /// <example>Created</example>
        [Required]
        [StringLength(100, MinimumLength = 1)]
        required public string Name { get; set; }

        /// <summary>
        /// Display text associated with the substate.
        /// </summary>
        /// <example>Created</example>
        [StringLength(maximumLength: 128)]
        public string? DisplayText { get; set; }

        /// <summary>
        /// Translations of the text used within the action definition.
        /// </summary>
        public IReadOnlyCollection<WorkflowTranslation>? I18n { get; set; }

        /// <summary>
        /// The actions that are available for the substate.
        /// </summary>
        [MaxLength(length: 100)]
        public IReadOnlyCollection<WorkflowAvailableAction>? AvailableActions { get; set; }
    }
}
