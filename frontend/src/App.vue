<script>
import {startIdleMaintenance,stopIdleMaintenance} from "@/services/modelWarmup"
import {startStudioNotifications,stopStudioNotifications} from "@/services/studioService"
export default {
  onShow: function () {
    startIdleMaintenance()
    startStudioNotifications()
  },
  onHide: function () {
    stopIdleMaintenance()
    stopStudioNotifications()
  },
}
</script>

<style>
@import './styles/theme.css';
/* #ifdef H5 */
*{margin:0;padding:0;box-sizing:border-box}
/* #endif */
view,text,image,button,input{margin:0;padding:0;box-sizing:border-box}button,input{outline:none}button{border:none;background:none}button::after{border:none}
</style>
