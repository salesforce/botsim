BotSIM System Design
####################################
The key design principles of BotSIM include modularity, extensibility and usability so that the toolkit can be easily adopted by both bot end users and developers. 
To achieve these, we adopt a layered design to decouple the development and the application. 
The toolkit comprises three layers, namely the infrastructure layer, the adaptor layer and the toolkit layer as shown in the figure below.

.. image:: _static/BotSIM_design.png
  :width: 550

Infrastructure Layer
**************************************************
The infrastructure layer is designed to offer fundamental functionalities for the framework. 
It comprises two major categories: the key models including natural language understanding (NLU), natural language generation (NLG) 
and the modules including the generator, the simulator and the remediator.

- ``botsim.models`` contains BotSIM's  NLU and NLG models. From a dialogue system perspective, BotSIM can be viewed as a counterpart to a chatbot: it needs to "understand" chatbot messages (NLU) and "respond" in natural languages (NLG). 
  Currently, fuzzy matching-based NLU and template-based NLG models are provided for efficiency reasons. Developers can also incorporate more advanced NLU and NLG models (see the `advanced usages <https://opensource.salesforce.com/botsim//latest/advanced_usage.html>`_ section). 
- ``botsim.modules`` consists of the three key  modules to power BotSIM's "generation-simulation-remediation" pipeline. 

    - ``botsim.modules.generator`` supports two major functionalities: 1) ``parser`` to parse bot metadata to infer dialog acts and dialog-act maps (BotSIM's NLU); 2) ``paraphraser`` to generate paraphrases of the input intent utterances. The paraphrases are used as intent queries of the simulation goals to probe bots' intent model.
    - ``botsim.modules.simulator`` implements the dialog-act level agenda-based user simulation in ``abus``. It also defines a simulation API client interface in ``simulation_client_base``. 
    - ``botsim.modules.remediator`` analyzes the simulation dialogs and produces the performance metrics and conversational analytics to support the dashboard visualisation. 

Adaptor Layer
**************************************************
Built on top of the infrastructure layer, the adaptor layer is designed for easy extension of BotSIM to new bot platforms. 
The two most important platform-specific components of the layer include:

- ``parser`` acts as an "adaptor" to unify bot definitions (e.g. dialog flows, intents/tasks) from different platforms to a common representation of dialog act maps. 
  The dialog act maps are used as BotSIM NLU to map  bot messages to dialog acts. 
  Note the implementations of the parser are highly platform-dependent and require bot developers to have access to bot APIs and design documentations. 
  We have provided our implementations of BotBuilder and DialogFlow CX parsers for reference.
- ``simulation_client`` is the other platform-dependent component for BotSIM to exchange conversations  with bots via APIs. 
  Similar to the ``parser``, the client implementation depends on the API designs of underlying bot platforms. 


Application Layer
**************************************************
The application layer is designed to significantly flatten the learning curves of applying BotSIM for both bot practitioners and end users. 

- ``botsim.cli`` contains a set of command line tools for practitioners to deep-dive into major stages of the BotSIM's  "generation-simulation-evaluation" pipeline. 
  The command line tools expose the required inputs and expected outputs for each stage, which serve as basic building blocks for bot practitioners to build their customized pipelines.
- ``botsim.streamlit_app`` is a multi-page easy-to-use Web app designed for direct application by bot end users such as bot admins without diving into technical details. 
  The app can be deployed as a docker container to cloud platforms for access to more computation resources. We use Streamlit for the App front-ends. Flask backend APIs are implemented to encapsulate
  major BotSIM functionalities. The app is also equipped with a SQL database to store  simulation stages and keep track of simulation performance across multiple platforms. 



Extending BotSIM to New Bot Platforms
#######################################
Bot developers can extend BotSIM to new platforms by implementing their platform-dependent ``adaptors`` including parsers and API clients. 

Parser
**************************************************************
The parser interface is defined in ``generator.parser`` and has the following important functions. 

1. ``extract_local_dialog_act_map`` function generates a “local” dialog act map by ignoring incoming and output  transitions. 
In other words, the local map only considers the messages/actions explicitly defined within the dialog. These local dialog act maps are modelled as graph nodes during 
the subsequent conversation graph modelling. In particular, the messages for the two special dialog acts, 
namely "intent_success_message"and "dialog_success_message" are also generated here according to heuristics discussed before.
2. ``conversation_graph_modelling`` models the entire bot design as a graph. Each individual dialog is represented by its local dialog act maps and included as the graph nodes. 
Transitions among dialogs are modelled as the graph edges. The graph modelling is based on the ``networkx`` package. 
There are two outputs from the function: the final dialog act maps and the graph data for conversation path visualisation.
3. ``parse`` function defines a general parser pipeline  starting from parsed local dialog act maps.

   .. code-block:: python

      def parse(self):
        # extract local dialog act maps which are later modelled as graph nodes
        local_dialog_act_maps = self.extract_local_dialog_act_map()
        self.dialog_act_maps, self.conv_graph_visualisation_data = self.conversation_graph_modelling(local_dialog_act_maps)
        self.dialog_with_intents_labels = set(self.dialog_act_maps.keys())
        self.dialog_ontology, self.customer_entities = self.extract_ontology()

These parser functions are highly platform dependent and the implementations are non-trivial. It is recommended to refer to bot platform and design documentation during development.  
We provide our parser implementations for the Einstein BotBuilder (``platform.botbuilder``) and Google DialogFlow CX (``platform.dialogflow_cx``) platforms.  
The utility functions supporting various parser functions are under  ``modules.generator.utils.<platform-name>/parser_utilities.py``

Given a new bot platform, developers can follow the following steps for implementing their new platform-specific parsers:

1. Refer to bot plaform or design documents or APIs of the platform to study how bot conversations are designed. Useful information includes

  - How user information is requested by bots in the bot design data
  - Relationship between bot messages and  actions for associating bot messages with dialog actions (request/inform)
  - What and how entities are requested in the bot messages. Together with the actions, a dialog act map entry can be inferred from the bot messages (e.g., request_Email)

2. Study the bot dialogs to understand their intents and identify the candidate messages for  “intent_success_messages” and “dialog_success_messages” 
3. Start by implementing ``modules.generator.utils.<new-platform-name>/parser_utilities.py`` to parse basic bot design elements to extract only dialog/intent information such as messages, actions, transitions. The main purposes of the utility functions include

    - associate bot messages with  actions, entities or dialog transitions
    - infer dialog acts from the actions and entities. 
   
   These utility functions are subsequently called by the ``extract_local_dialog_act_map`` function to produce the local dialog act maps. They are also responsible for extracting intent training utterances either from metadata (Einstein Bots) or API (Google DialogFlow CX).

4. Implement main parser functions.
5. Depending on the availability or accessibility of bot design documents, there might be multiple rounds of development of step 3 and 4.

Bot API Client 
**************************************************************
Similar to parsers, developers need to implement the API clients for their bot platforms if they are not yet supported.  
The client interface is defined in ``modules.simulator.simulation_client_base``   with the most important function ``perform_batch_simulation`` for permorning a batch of simulation 
episodes starting from ``simulation_goals[start_episode]``.  
A code snippet of a dialog loop is given below. Note the functions ``enqueue_bot_actions_from_bot_messages``, ``policy``, ``locate_simulation_errors``, ``log_episode_simulation_results`` of 
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

Adding New Rules to BotSIM Policy 
**************************************************************
The rules and the rule-based policy are defined in ``botsim.modules.simulator.user_simulator``. A new rule to respond to new bot dialog act named "<new-dialog-act>", 
can be added in the function ``_response_to_<new-dialog-act>``. The policy ``policy(bot_action)`` can be updated by including the  new rule.

Incorporating Advanced Models
#######################################


Natural Language Inference (NLI) Model as BotSIM NLU 
******************************************************
The natural language understanding component of BotSIM relies on fuzzy matching to convert bot messages to dialog acts. 
To handle bots that may be powered by a natural language generation model, the lexical-based fuzzy matching is not so reliable. The limitation can be circumvented by incorporating a semantic-based
NLU. A good candidate is to use a Natural Language Inference (NLI) model to compute the semantic matching scores of the bot messages with the ones in the dialog act maps.
The NLI model can be added as follows:

- Create a new subclass of ``botsim.models.nlu.nlu_model``
- Implement ``predict(bot_message, intent_name)`` function to map the ``bot_message`` to the best dialog act defined in the dialog named ``intent_name``
- Switch the ``nlu_model`` in the user simulator ``botsim.modules.simulator.abus`` to the new NLU model
- The NLI model scores can be interpolated with the fuzzy matching score to select the best dialog act

Neural-based NLG Model
************************************
To increase the naturalness and diversity of the template-based responses, a neural-based NLG model may be used to "paraphrase" the template messages. 
The model can be incorporated by following the following steps:

- Create a new NLG module under ``botsim.models.nlg``
- Implement ``generate(dialog_state)`` interface to take the semantic representation of dialog state and return a natural language response
- Change the ``nlg_model`` in the user simulator ``botsim.modules.simulator.abus`` with the new NLU model

Finetune T5 Paraphrasing Model
#######################################
To finetune the T5 paraphrasing model on users' in-domain data, please follow the following steps.

Prepare Paraphrase Pairs
*****************************
The training paraphrase pairs can be created by sampling real user queries with the same intents. The training data should be organized in the following json format: 

.. code-block:: json

    {
        {
            "text":" "<sos_s> <original text 1> <eos_s>"
            "paraphrase": "<sos_t> <paraphrased text 1> <eos_t>"
        },
        {
            "text":" "<sos_s> <original text 2> <eos_s>"
            "paraphrase": "<sos_t> <paraphrased text 2> <eos_t>"
        }
    }

To benchmark with the state-of-the-art `HRQ-VAE <https://github.com/tomhosking/hrq-vae>`_ model, the dev and test data (in jsonl format) can be directly downloaded from the repo.

Set Training Parameters
*****************************
The training parameters can be specified in the following ``train.json`` configuration file.

.. code-block:: json

    {
        "pretrained_path": "pretrained-model-path",
        "dropout": 0.1,
        "number_of_gpu": 4,
        "num_train_epochs": 100,
        "batch_size_per_gpu": 32,
        "test_batch_size_per_gpu": 32,
        "max_test_num_batches": 256,
        "alpha": 0.6,
        "test_path": "dev.jsonl",
        "save_path": "chpt-path",
        "train_path": "train.json",
        "optimizer": {
            "optimizer_name": "adam",
            "adam_epsilon": 1e-8,
            "learning_rate": 1e-4,
            "weight_decay": 0.0,
            "max_grad_norm": 1.0,
            "warmup_steps": 0,
            "gradient_accumulation_steps": 1
        }
    }

Customize Model and Trainer
*****************************
To make further changes to the T5 model and trainer, refer to the following files:

- Model definition: ``botsim.generator.paraphraser.t5_model``.
- T5 paraphraser trainer ``botsim.generator.paraphraser.train.py``.

GCP Deployment
###################
BotSIM Streamlit App can also be deployed to GCP for GPU access,  which will greatly accelerate the paraphrasing model inference process. 
The script for GCP deployment can be accessed at ``botsim/deploy/gcp/deploy_gcp_botsim_streamlit.sh``. The parameters  are as follows:

- ``cluster_name``: the name of users' gcp clusters for deployment
- ``project_name``: the project name
- ``user_name_space``: the user name space assigned by the gcp admin

The yaml configuration file for the deployment is ``botsim/deploy/gcp/deploy_gpu_streamlit_botsim.yaml``.  Users need to replace the following placeholders with their own values 
before use:

- ``<project-name>``: same as before
-  ``<deploy-name>`` and ``<service-name>`` denote the deployment and service names respectively

The number of GPUs and CPUs of the container can be set in the ``resources`` and ``tolerations`` sections. After successful deployment, the 
IP address of the service can be obtained from the ``external IP`` field of the result after issuing the following command:

.. code-block:: bash

    kubectl -n $user_name_space get services

The Streamlit App can now be accessed at ``https://<external-ip>:8501``