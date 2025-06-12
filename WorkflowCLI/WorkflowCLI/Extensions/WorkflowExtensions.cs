using FoggyBalrog.MermaidDotNet;
using FoggyBalrog.MermaidDotNet.StateDiagram;
using FoggyBalrog.MermaidDotNet.StateDiagram.Model;
using NationalInstruments.CommandLine.WorkflowCLI.Models;

namespace NationalInstruments.CommandLine.WorkflowCLI.Extensions
{
    public static class WorkflowExtensions
    {
        public static string TransformToMermaid(this Workflow workflow)
        {
            var diagramBuilder = Mermaid.StateDiagram();

            var states = new List<State>();
            var substates = new List<State>();
            var topLevelTransitions = new List<TopLevelTransition>();
            diagramBuilder.AddStates(workflow, states, substates, topLevelTransitions);
            diagramBuilder.AddTopLevelTransitions(substates, topLevelTransitions);
            return diagramBuilder.Build();
        }

        private static void AddTopLevelTransitions(
            this StateDiagramBuilder diagramBuilder,
            List<State> substates,
            List<TopLevelTransition> topLevelTransitions)
        {
            foreach (var transition in topLevelTransitions)
            {
                var fromState = substates.FirstOrDefault(x => x.Description == transition.From);
                var toState = substates.FirstOrDefault(x => x.Description == transition.To);
                if (fromState != null && toState != null)
                {
                    diagramBuilder.AddStateTransition(fromState, toState, transition.Action);
                }
                else
                {
                    Console.WriteLine($"Warning: Transition from {transition.From} to {transition.To} not found.");
                }
            }
        }

        private static void AddStates(
            this StateDiagramBuilder diagramBuilder,
            Workflow workflow,
            List<State> states,
            List<State> substates,
            List<TopLevelTransition> topLevelTransitions)
        {
            foreach (var state in workflow.States)
            {
                diagramBuilder.AddState(state, states, substates, topLevelTransitions);
            }
        }

        private static StateDiagramBuilder AddState(
            this StateDiagramBuilder builder,
            WorkflowState workflowState,
            List<State> states,
            List<State> substates,
            List<TopLevelTransition> topLevelTransitions)
        {
            var currentSubstates = new List<State>();
            var stateName = workflowState.Name.ToString().ToUpperInvariant();
            builder.AddCompositeState(stateName, out State topLevelState, (Action<StateDiagramBuilder>)(builder =>
            {
                builder.AddSubstates(workflowState, currentSubstates, stateName);
                builder.ProcessTransitions(workflowState, topLevelTransitions, currentSubstates, stateName);
            }));
            substates.AddRange(currentSubstates);
            return builder;
        }

        private static void ProcessTransitions(
            this StateDiagramBuilder builder,
            WorkflowState workflowState,
            List<TopLevelTransition> topLevelTransitions,
            List<State> currentSubstates,
            string stateName)
        {
            foreach (var fromSubstate in currentSubstates)
            {
                var workflowSubstate = workflowState.Substates.FirstOrDefault(x => $"{stateName}-{x.Name.ToUpperInvariant()}" == fromSubstate.Description);
                foreach (var availableAction in workflowSubstate.AvailableActions)
                {
                    if (workflowState.Name == availableAction.NextState)
                    {
                        builder.AddTransitionsWithinState(currentSubstates, stateName, fromSubstate, availableAction);
                    }
                    else
                    {
                        CreateTopLevelTransition(topLevelTransitions, fromSubstate, availableAction);
                    }
                }
            }
        }

        private static void AddSubstates(this StateDiagramBuilder builder, WorkflowState workflowState, List<State> currentSubstates, string stateName)
        {
            foreach (var workflowSubstate in workflowState.Substates)
            {
                var substate = builder.AddSubstate(currentSubstates, stateName, workflowSubstate);
                builder.ConditionallyAddDefaultTransition(workflowState, workflowSubstate, substate);
            }
        }

        private static State AddSubstate(
            this StateDiagramBuilder builder,
            List<State> currentSubstates,
            string stateName,
            WorkflowSubstate workflowSubstate)
        {
            builder.AddState($"{stateName}-{workflowSubstate.Name.ToUpperInvariant()}", out State substate);
            currentSubstates.Add(substate);
            return substate;
        }

        private static void ConditionallyAddDefaultTransition(
            this StateDiagramBuilder builder,
            WorkflowState workflowState,
            WorkflowSubstate workflowSubstate,
            State substate)
        {
            if (workflowSubstate.Name.ToUpperInvariant() == workflowState.DefaultSubstate.ToUpperInvariant())
            {
                builder.AddTransitionFromStart(substate);
            }
        }

        private static void CreateTopLevelTransition(
            List<TopLevelTransition> topLevelTransitions,
            State fromSubstate,
            WorkflowAvailableAction availableAction)
        {
            var topLevelTransition = new TopLevelTransition
            {
                From = fromSubstate.Description,
                To = $"{availableAction.NextState.ToString().ToUpperInvariant()}-{availableAction.NextSubstate.ToUpperInvariant()}",
                Action = GetActionName(availableAction)
            };
            topLevelTransitions.Add(topLevelTransition);
        }

        private static void AddTransitionsWithinState(
            this StateDiagramBuilder builder,
            List<State> currentSubstates,
            string stateName,
            State fromSubstate,
            WorkflowAvailableAction availableAction)
        {
            var toSubstate = currentSubstates.FirstOrDefault(x => x.Description == $"{stateName}-{availableAction.NextSubstate.ToUpperInvariant()}");
            string actionName = GetActionName(availableAction);
            builder.AddStateTransition(fromSubstate, toSubstate, actionName);
        }

        private static string GetActionName(WorkflowAvailableAction availableAction)
        {
            return availableAction.Action + (availableAction.ShowInUI ? string.Empty : " _(hidden)_");
        }

        private record TopLevelTransition
        {
            internal string From { get; set; } = string.Empty;
            internal string To { get; set; } = string.Empty;
            internal string Action { get; set; } = string.Empty;
        }
    }
}
