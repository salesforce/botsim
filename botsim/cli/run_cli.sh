#!/bin/bash

#platform=Einstein_Bot
#api_credential='config/botbuilder/liveagent.api.token.json'
#api_credential='config/dialogflow_cx_travel.json'
num_t5_paraphrases=16
num_pegasus_paraphrases=16

while [ -n "$1" ]; do
  case "$1" in
  --platform) platform="$2"
    shift;;
  --test_name) name="$2"
    shift ;;
  --bot_api) api_credential=$2
    shift;;
  --num_seed_utterances) num_seed_utterances=$2
    shift;;
  --num_t5_paraphrases) num_t5_paraphrases=$2
    shift;;
  --num_pegasus_paraphrases) num_pegasus_paraphrases=$2
    shift;;
  --max_num_simulations) max_num_simulations=$2
    shift;;
  --max_num_dialog_turns) max_num_dialog_turns=$2
    shift;;
  --stage) stage=$2
    shift;;
  esac
  shift
done

export PYTHONPATH=./:$PYTHONPATH
if [ -z $platform ]; then
    echo "usage: $0 platform name bot_api num_seed_utterances num_t5_paraphrases num_pegasus_paraphrases max_num_simulations max_num_dialog_turns stage"
    exit 1
fi

echo "$0 $platform $name $api_credential $num_t5_paraphrases $num_pegasus_paraphrases $stage"
if [ $stage -eq 0 ]; then
    if [ -z $api_credential ]; then
        echo "usage: $0 platform name bot_api(required) num_t5_paraphrases num_pegasus_paraphrases stage"
        exit 1
    fi
    echo "==========Creating configuration file=========="
    python botsim/cli/prepare_botsim.py \
       --platform $platform \
       --api_credential $api \
       --test_name $test_id \
       --num_seed_utterances $num_seed_utterances \
       --num_t5_paraphrases $num_t5_paraphrases \
       --num_pegasus_paraphrases $num_pegasus_paraphrases \
       --max_num_simulations $max_num_simulations \
       --max_num_dialog_turns $max_num_dialog_turns \
       --metadata_botversions config/botbuilder/TemplateBotSIM150.bot \
       --metadata_intent_utterances config/botbuilder/TemplateBotSIM_intent_sets.mlDomain
fi
if [ $stage -eq 1 ]; then
    echo "==========Parsing bot=========="
    python botsim/cli/run_generator_parser.py \
       --platform $platform \
       --test_name $name
    echo "==========Parsing finished. See results under data/$platform/$name/conf/=========="
fi
if [ $stage -eq 2 ]; then
    echo "==========Apply paraphrasing to intent utterances=========="
    echo "==========Change settings at data/$platform/$name/conf/config.json =========="
    python botsim/cli/run_generator_paraphraser.py \
       --platform $platform \
       --test_name $name
fi
if [ $stage -eq 3 ]; then
    echo "==========Generate simulation goals=========="
    python botsim/cli/run_generator_goal_generation.py \
       --platform $platform \
       --test_name $name
fi
if [ $stage -eq 4 ]; then
    echo "==========Dialog simulation=========="
    python botsim/cli/run_simulator.py \
       --platform $platform \
       --test_name $name
fi
if [ $stage -eq 5 ]; then
    echo "==========Result analysis and remediation=========="
    python botsim/cli/run_remediator.py \
      --platform $platform \
      --test_name $name
fi
