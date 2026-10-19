<script>
import {trimOwnedFiles} from "@/services/ownedFiles"
import {startStudioNotifications,stopStudioNotifications} from "@/services/studioService"
export default {
  onLaunch: function () {
    trimOwnedFiles({materials:true}).catch(()=>{})
  },
  onShow: function () {
    startStudioNotifications()
  },
  onHide: function () {
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
