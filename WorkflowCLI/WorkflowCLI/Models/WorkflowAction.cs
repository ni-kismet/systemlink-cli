using System.ComponentModel.DataAnnotations;

namespace NationalInstruments.CommandLine.WorkflowCLI.Models
{
    /// <summary>
    /// Defines an action for a workflow.
    /// </summary>
    public class WorkflowAction
    {
        /// <summary>
        /// Name of the action.
        /// </summary>
        /// <example>Deploy test</example>
        [Required]
        [StringLength(maximumLength: 128, MinimumLength = 1)]
        required public string Name { get; set; }

        /// <summary>
        /// Display text associated with the action.
        /// </summary>
        /// <example>Deploy test</example>
        [Required]
        [StringLength(maximumLength: 128, MinimumLength = 1)]
        required public string DisplayText { get; set; }

        /// <summary>
        /// The icon to display next to the display text.
        /// </summary>
        public WorkflowActionIcon? IconClass { get; set; }

        /// <summary>
        /// Translations of the text used within the action definition.
        /// </summary>
        public IReadOnlyCollection<WorkflowTranslation>? I18n { get; set; }

        /// <summary>
        /// The resources for which the user must have the `testPlan:ExecuteWithSpecificity` privilege.
        /// The user must also have the `testPlan:Execute` privilege.
        /// </summary>
        /// <example>Deploy</example>
        public IReadOnlyCollection<string>? PrivilegeSpecificity { get; set; }

        /// <summary>
        /// The execution definition associated with the action.
        /// </summary>
        [Required]
        required public ExecutionDefinitionBase ExecutionAction { get; set; }
    }
}
