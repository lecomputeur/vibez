"""Pure report gates: counters/load events cannot substitute for rendered pixels."""
BLUE=[37,99,235,255]

def check_chart(state, count, expected):
    fixed=(state.get('chartCount')==count and sorted(state.get('ready',[]))==list(range(count))
           and state.get('attempts')==[1]*count and state.get('scriptMessages')==count
           and state.get('validatedPixels')==[BLUE]*count and state.get('tableRows')==4)
    old=(state.get('chartCount')==count and state.get('ready')==[]
         and state.get('scriptMessages')==0 and state.get('validatedPixels')==[]
         and len(state.get('attempts',[]))==count and all(n>=10 for n in state['attempts'])
         and state.get('tableRows')==4)
    return {'expectedStatePassed':bool(state.get('finished') and (fixed if expected=='fixed' else old)),
            'fixedContractPassed':bool(state.get('finished') and fixed)}
