<script>
export default {
  onLaunch: function () {
    console.log('App Launch')
  },
  onShow: function () {
    console.log('App Show')
  },
  onHide: function () {
    console.log('App Hide')
  },
}
</script>

<style>
	/*每个页面公共css */
	* {
		margin: 0;
		padding: 0;
		box-sizing: border-box;
	}
	
	page {
		background: linear-gradient(135deg, #ff6b6b, #ffa500);
		min-height: 100vh;
	}
	
	/* 全局按钮样式重置 */
	button {
		border: none;
		outline: none;
		background: none;
	}
	
	button::after {
		border: none;
	}
	
	/* 全局输入框样式 */
	input {
		outline: none;
		border: none;
	}
</style>
