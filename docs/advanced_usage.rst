Extending BotSIM to new bot platforms
#######################################
Bot developers can extend BotSIM to new platforms by implementing their platform-dependent parsers and API clients. 
They serve as the “adaptors” in order to apply BotSIM’s “generation-simulation-remediation” pipeline.

Parser
**************************************************************
The parser interface is defined in generator.parser and has the following important functions to implement. 
As these functions are highly platform dependent, the implementation might be non-trivial and require access to bot design documentation from the bot platform provider.  
We provide our initial parser implementations for the Einstein BotBuilder (``platform.botbuilder``) and Google DialogFlow CX (``platform.dialogflow_cx``) platforms.  
The utility functions supporting the parsers are under  ``modules.generator.utils.<platform-name>/parser_utilities.py``

1. ``extract_local_dialog_act_map`` function generates a “local” dialog act map by ignoring incoming and output  transitions. In other words, the local map only considers the messages/actions explicitly defined within the dialog. These local dialog act maps are modelled as graph nodes during the subsequent conversation graph modelling. In particular, the messages for the two special dialog acts, namely "intent_success_message"and "dialog_success_message" are also generated here according to the following heuristics:   "intent_success_message" contains the first request message and all its previous normal messages    "dialog_success_message" contains the last messages.
2. ``conversation_graph_modelling`` models the entire bot design as a graph. Each individual dialog is represented by its local dialog act maps and modelled as the graph nodes. Transitions among the individual dialogs are modelled as the graph edges. The graph modelling is based on the ``networkx`` package. There are two outputs from the function: the final dialog act maps and the graph data for conversation path visualisation.
3. ``parse`` function defines a general parser pipeline for all platforms starting from parsed local dialog act maps.

   .. code-block:: python

      def parse(self):
        # extract local dialog act maps which are later modelled as graph nodes
        local_dialog_act_maps = self.extract_local_dialog_act_map()
        self.dialog_act_maps, self.conv_graph_visualisation_data = self.conversation_graph_modelling(local_dialog_act_maps)
        self.dialog_with_intents_labels = set(self.dialog_act_maps.keys())
        self.dialog_ontology, self.customer_entities = self.extract_ontology()

Given a new bot platform, developers can follow the following steps for implementing their new platform-specific parsers:

1. Refer to bot design documents or APIs of the platform to study how bot dialogs are designed. Useful information includes

  1. How user information is requested by bots
  2. Relationship between bot messages and  actions to associate bot messages to dialog actions (request/inform)
  3. What entities are requested in the bot messages. Together with the actions, a dialog act map entry can be inferred from the bot messages (e.g., request_Email)

2. Study the bot dialogs to understand their intents and identify the candidate messages for  “intent_success_messages” and “dialog_success_messages” 
3. Inferring dialog acts: implement ``modules.generator.utils.<new-platform-name>/parser_utilities.py`` to parse dialog related bot design elements to extract only dialog/intent information such as messages, actions, transitions. 

The goal is to

  1. associate bot messages with  actions, entities, dialog transitions
  2. infer dialog acts for each dialog from the actions and entities. These utility functions are subsequently called by the ``extract_local_dialog_act_map`` function  to produce the local dialog act maps. They are also responsible for extracting intent training utterances either from metadata (Einstein Bots) or API (Google DialogFlow CX).

4. Implement parser functions: start implementation for extracting the local dialog act maps, final dialog act maps and the ontologies.
5. Depending on the availability or accessibility of bot design documents, there might be multiple rounds of development of step 3 and 4.

Bot API client 
**************************************************************
The BotSIM Simulator performs dialog simulation by calling bot APIs. Similar to the parsers, developers need to implement the API clients for their bot platforms.  
The interface is defined in ``modules.simulator.simulation_client_base``   with the most important function ``perform_batch_simulation`` which performs a batch of simulation episodes starting from ``simulation_goals[start_episode]``.  
A code snippet of the dialog loop is given below. Note the functions ``enqueue_bot_actions_from_bot_messages``, ``policy``, ``locate_simulation_errors``, ``log_episode_simulation_results`` of 
``user_simulator`` are platform-agnostic and can be shared by all bot platforms.

.. code-block:: python
    
   while episode_index < len(simulation_goals):
        user_simulator.reset(start_episode) 
        session_finished = False
        # a conversation loop between BotSIM and the bot
        while not session_finished:
            # The simulator (shared by all platforms) parses a list of consecutive
            # bot messages into a queue of semantic-level actions. BotSIM subsequently
            # response to such actions one by one.
            status = user_simulator.enqueue_bot_actions_from_bot_messages(
                "DialogFlow CX",  # name of the bot
                bot_messages,     # current bot messages
                bot_action_frame, # current dialog state 
                start_episode, 
                self.dialog_logs)
        # Response to all bot_actions one by one
            for bot_action in user_simulator.state["bot_action_queue"]:
                if user_simulator.state["action"] == "fail":
                    self.dialog_logs[start_episode]["chat_log"].append(bot_messages)
                    result = user_simulator.locate_simulation_errors()
                    session_finished = True
                elif user_simulator.state["action"] == "success":
                    self.dialog_logs[start_episode]["chat_log"].append(bot_messages)
                    session_finished = True
            
                if session_finished:
                    episode_success, episode_intent_error, episode_ner_error, \
                    episode_other_error, episode_turns = \ 
                    user_simulator.log_episode_simulation_results(
                    result, start_episode, self.dialog_logs, self.dialog_errors)
                    break
                # apply BotSIM rule-based policy to get natural language BotSIM message
                botsim_action, botsim_message, botsim_response_slots = \
                    user_simulator.policy(bot_action)
                # Send BotSIM message back to bot via API to continue conversation
                if len(botsim_message) > 0:
                    text_input = session.TextInput(text=botsim_message)
                    query_input = session.QueryInput(text=text_input, language_code="en")
                    try:
                        request = session.DetectIntentRequest(session=session_id, query_input=query_input)
                        response = session_client.detect_intent(request=request)
                    except InvalidArgument:
                        raise

                new_bot_message = [" ".join(txt.replace("\n", "").split())
                                for msg in response.query_result.response_messages
                                for txt in msg.text.text]
                bot_messages = new_bot_message
            episode_index += 1

Incorporating advanced models
#######################################
For efficiency reasons, the dialog components of BotSIM are all based on templates (dialog act maps for NLU, response templates for NLG).
To accommodate dialog act-level agenda-based dialog simulation, rule-based policy is adopted. Nevertheless, more advanced models can also be incorporated.

Natural Language Inference (NLI) model as BotSIM NLU 
******************************************************
The natural language understanding component of BotSIM relies on fuzzy matching to convert bot messages to dialog acts. 
To cope with bots that may be powered by a natural language generation model, the lexical-based fuzzy matching is not enough. The limitation can be circumvented by incorporating a semantic-based
NLU. A good candidate is to use a Natural Language Inference (NLI) model to compute the matching scores of the bot messages with the ones in the dialog act maps.
The NLI model can be added by  the following steps:

- Create a new subclass of ``botsim.models.nlu.nlu_model``
- Implement ``predict(bot_message, intent_name)`` function to map the ``bot_message`` to the best dialog act defined in the dialog named ``intent_name``
- Change the ``nlu_model`` in the user simulator ``botsim.modules.simulator.abus`` with the new NLU model

Neural-based NLG model
************************************
To increase the naturalness of the template-based responses, a neural-based NLG model may be used to convert the template messages to be more natural. 
The model can be incorporated by following the steps below:

- Create a new NLG module under ``botsim.models.nlg``
- Implement ``generate(dialog_state)`` interface to take the semantic representation of dialog state and return a natural language response
- Change the ``nlg_model`` in the user simulator ``botsim.modules.simulator.abus`` with the new NLU model



